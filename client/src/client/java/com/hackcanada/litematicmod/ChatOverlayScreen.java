package com.hackcanada.litematicmod;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.reflect.TypeToken;
import com.hackcanada.claudecraft.BackendClient;
import com.hackcanada.claudecraft.ClaudeCraft;
import com.hackcanada.claudecraft.SchematicHelper;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.TextFieldWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.text.Text;
import net.minecraft.util.math.BlockPos;
import org.lwjgl.glfw.GLFW;

import java.io.*;
import java.lang.reflect.Type;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.file.*;
import java.util.*;

public class ChatOverlayScreen extends Screen {

    // ── Layout — ChatGPT style: sidebar left + chat right ──────────────────
    private static final int SIDEBAR_W     = 115;
    private static final int CHAT_W        = 280;
    private static final int TOTAL_W       = SIDEBAR_W + CHAT_W;
    private static final int TOTAL_H       = 270;  // extra 10px so buttons aren't clipped
    private static final int PAD           = 8;
    private static final int BOT_PAD       = 10;   // extra bottom breathing room
    private static final int INPUT_H       = 20;
    private static final int BTN_H         = 20;
    private static final int BTN_W         = (CHAT_W - PAD * 2 - 4) / 2;
    private static final int LINE_H        = 12;
    private static final int MAX_HISTORY   = 200;
    private static final int MAX_SESSIONS  = 8;
    private static final int ROW_H         = 18;   // session row height
    // Sidebar row icon widths: rename + delete
    private static final int ICON_W        = 14;
    private static final int ICON_GAP      = 2;
    // Y where session list starts (below header + divider + new-chat btn)
    // header text ~9px, divider at +14, gap 4, new-chat btn BTN_H, gap 4
    private static final int ROW_START_OFF = 14 + 4 + BTN_H + 6; // offset from pt

    // Colors
    private static final int C_WHITE        = 0xFFFFFFFF;
    private static final int C_AI           = 0xFFCC77FF;
    private static final int C_SYS          = 0xFFAAAAAA;
    private static final int C_CHAT_BG      = (int) 0xEE0D0D14;
    private static final int C_SIDEBAR_BG   = (int) 0xEE07070E;
    private static final int C_DIVIDER      = (int) 0x55FFFFFF;
    private static final int C_ROW_ACT      = (int) 0xFF1E3A5F;
    private static final int C_HDR          = 0xFF8888AA;
    private static final int C_RENAME_BG    = (int) 0xFF0D2040;
    private static final int C_TAB_ACT      = (int) 0xFF1A2A4A;
    private static final int C_TAB_INACTIVE = (int) 0xFF0D1020;

    // ── Tab state ────────────────────────────────────────────────────────────
    /** 0 = Chat tab, 1 = Schematic (load by name) tab, 2 = My Files tab */
    private static int activeTab = 0;

    // ── Schematic panel state ────────────────────────────────────────────────
    private TextFieldWidget schematicField;

    // ── Streaming build state (BUILD_START … BUILD_LAYER … BUILD_DONE) ───────
    /** Name of the schematic currently being streamed, or null when idle. */
    private static String buildingName = null;
    /** Accumulated blocks from BUILD_LAYER packets: list of {x,y,z,block} JsonObjects. */
    private static final List<JsonObject> pendingBlocks = new ArrayList<>();
    /** Number of layers expected (from BUILD_START). */
    private static int buildTotalLayers = 0;
    /** Number of BUILD_LAYER packets received so far. */
    private static int buildLayersReceived = 0;

    // ── Persistence ─────────────────────────────────────────────────────────
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    private static Path historyFile() {
        return MinecraftClient.getInstance().runDirectory.toPath()
                .resolve("claudecraft_history.json");
    }

    static class SaveData {
        int nextId = 1;
        List<Session> sessions = new ArrayList<>();
    }

    static class Session {
        String name;
        List<String> messages = new ArrayList<>();
        Session(String name) { this.name = name; }
    }

    // ── Persistent state ─────────────────────────────────────────────────────
    static List<Session> allSessions    = new ArrayList<>();
    static int           activeSession  = 0;
    static int           nextSessionId  = 1;   // auto-incrementing counter for names

    private static BackendClient persistentClient;
    private static long lastConnectAttemptMs = 0;
    private static final long RECONNECT_COOLDOWN_MS = 5000;

    // ── Per-instance widgets ─────────────────────────────────────────────────
    private TextFieldWidget inputField;
    private ButtonWidget    sendButton;
    private ButtonWidget    buildButton;

    /** Index of the session currently being renamed, -1 = none. */
    private int renamingSession = -1;
    /** The active rename field (added as drawable so focus works). */
    private TextFieldWidget renameField;

    public ChatOverlayScreen() { super(Text.literal("AI Chat")); }

    // ── Layout helpers ───────────────────────────────────────────────────────
    private int left()     { return (this.width  - TOTAL_W) / 2; }
    /** Always keep the panel fully inside the screen — clamped on both top and bottom. */
    private int top() {
        int centered = (this.height - TOTAL_H) / 2;
        // At least 4px from top, at least 4px from bottom
        return Math.max(4, Math.min(centered, this.height - TOTAL_H - 4));
    }
    private int chatLeft() { return left() + SIDEBAR_W; }

    private static List<String> currentMessages() {
        if (allSessions.isEmpty()) newSession();
        return allSessions.get(activeSession).messages;
    }

    // ── Disk I/O ─────────────────────────────────────────────────────────────
    static void loadHistory() {
        Path f = historyFile();
        if (!Files.exists(f)) { newSession(); return; }
        try (Reader r = Files.newBufferedReader(f)) {
            SaveData data = GSON.fromJson(r, SaveData.class);
            if (data != null && data.sessions != null && !data.sessions.isEmpty()) {
                allSessions   = data.sessions;
                nextSessionId = Math.max(data.nextId, allSessions.size() + 1);
                activeSession = allSessions.size() - 1;
                return;
            }
        } catch (Exception e) {
            // try legacy format (plain List<Session>)
            try (Reader r = Files.newBufferedReader(f)) {
                Type t = new TypeToken<List<Session>>(){}.getType();
                List<Session> loaded = GSON.fromJson(r, t);
                if (loaded != null && !loaded.isEmpty()) {
                    allSessions   = loaded;
                    nextSessionId = loaded.size() + 1;
                    activeSession = allSessions.size() - 1;
                    return;
                }
            } catch (Exception ignored) {}
            ClaudeCraft.LOGGER.warn("Could not load chat history: {}", e.getMessage());
        }
        newSession();
    }

    static void saveHistory() {
        try {
            Path f = historyFile();
            Files.createDirectories(f.getParent());
            SaveData data = new SaveData();
            data.nextId   = nextSessionId;
            data.sessions = allSessions;
            try (Writer w = Files.newBufferedWriter(f)) {
                GSON.toJson(data, w);
            }
        } catch (Exception e) {
            ClaudeCraft.LOGGER.warn("Could not save chat history: {}", e.getMessage());
        }
    }

    static void newSession() {
        String name = "Chat " + nextSessionId++;
        allSessions.add(new Session(name));
        activeSession = allSessions.size() - 1;
        while (allSessions.size() > MAX_SESSIONS) allSessions.remove(0);
        if (activeSession >= allSessions.size()) activeSession = allSessions.size() - 1;
        saveHistory();
    }

    static void deleteSession(int idx) {
        if (allSessions.size() <= 1) {
            // keep at least one — just clear it and reset its number
            allSessions.get(0).messages.clear();
            allSessions.get(0).name = "Chat 1";
            nextSessionId = 2;
            activeSession = 0;
            saveHistory();
            return;
        }
        allSessions.remove(idx);
        // Renumber all remaining "Chat N" sessions sequentially from 1
        nextSessionId = 1;
        for (Session s : allSessions) {
            if (s.name.matches("Chat \\d+")) {
                s.name = "Chat " + nextSessionId;
            }
            nextSessionId++;
        }
        if (activeSession >= allSessions.size()) activeSession = allSessions.size() - 1;
        if (activeSession < 0) activeSession = 0;
        saveHistory();
    }

    // ── Lifecycle ────────────────────────────────────────────────────────────
    @Override
    protected void init() {
        super.init();

        if (allSessions.isEmpty()) loadHistory();
        if (currentMessages().isEmpty()) {
            currentMessages().add("[System] Type a message and press Send or Enter.");
            currentMessages().add("[System] Use Build to ask the AI to build something.");
        }

        ensureConnected();

        int cl  = chatLeft();
        int sl  = left();
        int pt  = top();
        int pb  = pt + TOTAL_H;
        int btnY   = pb  - BOT_PAD - BTN_H;
        int inputY = btnY - PAD - INPUT_H;

        // ── Tab buttons (Chat | Schematic | My Files) ────────────────────────
        int tabW = (CHAT_W - PAD * 2) / 3;
        int tabY = pt + 1;
        this.addDrawableChild(ButtonWidget.builder(Text.literal("Chat"), btn -> {
            activeTab = 0;
            this.clearAndInit();
        }).dimensions(cl + PAD, tabY, tabW - 2, 16).build());
        this.addDrawableChild(ButtonWidget.builder(Text.literal("Schematic"), btn -> {
            activeTab = 1;
            this.clearAndInit();
        }).dimensions(cl + PAD + tabW, tabY, tabW - 2, 16).build());
        this.addDrawableChild(ButtonWidget.builder(Text.literal("My Files"), btn -> {
            activeTab = 2;
            this.clearAndInit();
        }).dimensions(cl + PAD + tabW * 2, tabY, tabW - 2, 16).build());

        if (activeTab == 0) {
            // ── CHAT TAB ─────────────────────────────────────────────────────

            // ── Chat input field
            inputField = new TextFieldWidget(
                    this.textRenderer, cl + PAD, inputY,
                    CHAT_W - PAD * 2, INPUT_H,
                    Text.literal("Message ClaudeCraft..."));
            inputField.setMaxLength(512);
            inputField.setDrawsBackground(true);
            inputField.setPlaceholder(Text.literal("Message ClaudeCraft..."));
            this.addSelectableChild(inputField);
            this.setInitialFocus(inputField);

            // ── Send / Build buttons
            sendButton = ButtonWidget.builder(Text.literal("Send"), btn -> onSend())
                    .dimensions(cl + PAD, btnY, BTN_W, BTN_H).build();
            buildButton = ButtonWidget.builder(Text.literal("Build"), btn -> onBuild())
                    .dimensions(cl + PAD + BTN_W + 4, btnY, BTN_W, BTN_H).build();
            sendButton.active  = false;
            buildButton.active = false;
            this.addDrawableChild(sendButton);
            this.addDrawableChild(buildButton);

        } else if (activeTab == 1) {
            // ── SCHEMATIC TAB ─────────────────────────────────────────────────
            inputField = null; sendButton = null; buildButton = null;

            // Instructions label is drawn in render()
            // Schematic name / paste field
            int fieldY = pt + 40;
            schematicField = new TextFieldWidget(
                    this.textRenderer, cl + PAD, fieldY,
                    CHAT_W - PAD * 2, INPUT_H,
                    Text.literal("Schematic name..."));
            schematicField.setMaxLength(256);
            schematicField.setDrawsBackground(true);
            schematicField.setPlaceholder(Text.literal("Paste schematic name here..."));
            this.addDrawableChild(schematicField);
            this.setInitialFocus(schematicField);

            // Load button
            int loadBtnY = fieldY + INPUT_H + 6;
            this.addDrawableChild(ButtonWidget.builder(Text.literal("Load Schematic"), btn -> onLoadSchematic())
                    .dimensions(cl + PAD, loadBtnY, CHAT_W - PAD * 2, BTN_H).build());

            // Build via AI button
            int buildAiBtnY = loadBtnY + BTN_H + 4;
            this.addDrawableChild(ButtonWidget.builder(Text.literal("Build via AI"), btn -> onBuildSchematic())
                    .dimensions(cl + PAD, buildAiBtnY, CHAT_W - PAD * 2, BTN_H).build());

        } else if (activeTab == 2) {
            // ── MY FILES TAB ──────────────────────────────────────────────────
            inputField = null; sendButton = null; buildButton = null;

            // Scan both litematics/ and schematics/ folders for .litematic files
            List<Path> files = scanLitematicFolders();

            int fileRowY = pt + 24;  // start just below the tab bar
            int fileRowH = 18;
            int fileW    = CHAT_W - PAD * 2;

            if (files.isEmpty()) {
                // Nothing to show — instruction text drawn in render()
            } else {
                for (Path f : files) {
                    if (fileRowY + fileRowH > pb - PAD) break;  // clamp to panel
                    String stem = f.getFileName().toString()
                            .replaceAll("\\.litematic$", "");
                    String folder = f.getParent().getFileName().toString(); // "litematics" or "schematics"
                    String label  = truncate("[" + folder.charAt(0) + "] " + stem, fileW - 4);
                    final Path filePath = f;
                    final String stemFinal = stem;
                    final Path parentFinal = f.getParent();
                    final int rowY = fileRowY;
                    this.addDrawableChild(ButtonWidget.builder(Text.literal(label), btn -> {
                        onLoadFileSchematic(stemFinal, parentFinal);
                    }).dimensions(cl + PAD, rowY, fileW, fileRowH).build());
                    fileRowY += fileRowH + 2;
                }
            }
        }

        // ── "+ New Chat" button — sits below the "Chats" header + divider
        int newBtnY = pt + 18;   // header text 9px + divider at 14 + 4 gap
        this.addDrawableChild(ButtonWidget.builder(Text.literal("+ New Chat"), btn -> {
            renamingSession = -1;
            newSession();
            this.clearAndInit();
        }).dimensions(sl + PAD, newBtnY, SIDEBAR_W - PAD * 2, BTN_H).build());

        // ── Session rows (newest first), starting below the new-chat button
        int rowStartY = newBtnY + BTN_H + 4;
        int labelW    = SIDEBAR_W - PAD * 2 - ICON_W - ICON_GAP - ICON_W - ICON_GAP;

        for (int i = allSessions.size() - 1; i >= 0; i--) {
            final int idx = i;
            int rowY = rowStartY + (allSessions.size() - 1 - i) * (ROW_H + 2);
            if (rowY + ROW_H > pb - PAD) break;

            // If this row is being renamed, skip normal buttons — we draw a field instead
            if (renamingSession == idx) continue;

            String label = truncate(allSessions.get(i).name, labelW);
            int iconX = sl + PAD + labelW + ICON_GAP;

            this.addDrawableChild(ButtonWidget.builder(Text.literal(label), btn -> {
                renamingSession = -1;
                activeSession   = idx;
                this.clearAndInit();
            }).dimensions(sl + PAD, rowY, labelW, ROW_H).build());

            // ✎ rename icon
            this.addDrawableChild(ButtonWidget.builder(Text.literal("\u270E"), btn -> {
                renamingSession = idx;
                this.clearAndInit();
            }).dimensions(iconX, rowY, ICON_W, ROW_H).build());

            // × delete icon
            this.addDrawableChild(ButtonWidget.builder(Text.literal("\u00D7"), btn -> {
                renamingSession = -1;
                deleteSession(idx);
                this.clearAndInit();
            }).dimensions(iconX + ICON_W + ICON_GAP, rowY, ICON_W, ROW_H).build());
        }

        // ── Rename inline field — added as DRAWABLE so keyboard focus works
        renameField = null;
        if (renamingSession >= 0 && renamingSession < allSessions.size()) {
            int rowIdx = allSessions.size() - 1 - renamingSession;
            int rowY   = rowStartY + rowIdx * (ROW_H + 2);

            renameField = new TextFieldWidget(
                    this.textRenderer,
                    sl + PAD, rowY,
                    SIDEBAR_W - PAD * 2, ROW_H,
                    Text.literal("Rename..."));
            renameField.setMaxLength(40);
            renameField.setDrawsBackground(true);
            renameField.setText(allSessions.get(renamingSession).name);
            renameField.setSelectionStart(0);
            renameField.setSelectionEnd(renameField.getText().length());
            renameField.setFocused(true);
            this.addDrawableChild(renameField);   // drawable = focus + render both work
            this.setFocused(renameField);
        }
    }

    // ── Tick — keep button state in sync with input ──────────────────────────
    @Override
    public void tick() {
        super.tick();
        if (activeTab == 0 && inputField != null && sendButton != null && buildButton != null) {
            boolean hasText = !inputField.getText().trim().isEmpty();
            sendButton.active  = hasText;
            buildButton.active = hasText;
        }
    }

    // ── Connection ───────────────────────────────────────────────────────────
    private void ensureConnected() {
        if (persistentClient != null && persistentClient.isOpen()) return;
        if (persistentClient != null &&
                persistentClient.getReadyState() == org.java_websocket.enums.ReadyState.CLOSING) return;
        long now = System.currentTimeMillis();
        if (now - lastConnectAttemptMs < RECONNECT_COOLDOWN_MS) return;
        lastConnectAttemptMs = now;
        try {
            persistentClient = new BackendClient(
                    new URI("ws://127.0.0.1:8080"),
                    ChatOverlayScreen::handleIncomingMessage);
            persistentClient.connect();
        } catch (URISyntaxException e) {
            ClaudeCraft.LOGGER.error("Invalid WebSocket URI", e);
        }
    }

    // ── Messages ─────────────────────────────────────────────────────────────
    private static void handleIncomingMessage(String message) {
        MinecraftClient.getInstance().execute(() -> {
            // ── Legacy plain-text LOAD_SCHEMATIC command ───────────────────
            if (message.startsWith("LOAD_SCHEMATIC ")) {
                String fn = message.substring("LOAD_SCHEMATIC ".length()).trim();
                addMessage("[Schematic] Loading: " + fn);
                MinecraftClient mc = MinecraftClient.getInstance();
                if (mc.player != null) {
                    mc.player.sendMessage(Text.literal("[ClaudeCraft] Loading: " + fn), false);
                    SchematicHelper.loadLitematica(mc.world, mc.player.getBlockPos(), fn);
                }
                return;
            }

            // ── Try to parse as JSON (BUILD_START / BUILD_LAYER / BUILD_DONE) ─
            if (message.startsWith("{")) {
                try {
                    JsonObject obj = JsonParser.parseString(message).getAsJsonObject();
                    String type = obj.has("type") ? obj.get("type").getAsString() : "";

                    switch (type) {
                        case "BUILD_START": {
                            buildingName        = obj.has("name") ? obj.get("name").getAsString() : "streamed";
                            buildTotalLayers    = obj.has("totalLayers") ? obj.get("totalLayers").getAsInt() : 0;
                            buildLayersReceived = 0;
                            pendingBlocks.clear();
                            addMessage("[Build] Starting: " + buildingName
                                    + " (" + buildTotalLayers + " layers)");
                            return;
                        }
                        case "BUILD_LAYER": {
                            if (obj.has("blocks")) {
                                JsonArray blocks = obj.get("blocks").getAsJsonArray();
                                blocks.forEach(e -> pendingBlocks.add(e.getAsJsonObject()));
                            }
                            buildLayersReceived++;
                            // Progress update every 10 layers
                            if (buildTotalLayers > 0 && buildLayersReceived % 10 == 0) {
                                addMessage("[Build] Layer " + buildLayersReceived
                                        + "/" + buildTotalLayers);
                            }
                            return;
                        }
                        case "BUILD_DONE": {
                            // All layers received — write a .litematic file then load it
                            String name = buildingName != null ? buildingName : "streamed";
                            addMessage("[Build] Done! " + pendingBlocks.size()
                                    + " blocks — loading via Litematica…");
                            writeLitematicAndLoad(name, new ArrayList<>(pendingBlocks));
                            buildingName = null;
                            pendingBlocks.clear();
                            return;
                        }
                        default:
                            break;
                    }
                } catch (Exception e) {
                    ClaudeCraft.LOGGER.warn("Could not parse incoming JSON: " + e.getMessage());
                }
            }

            // ── Plain-text AI chat reply ───────────────────────────────────
            addMessage("AI: " + message);
        });
    }

    /**
     * Converts the accumulated list of block JsonObjects into a real .litematic
     * file (written to {@code .minecraft/litematics/<name>.litematic}), then
     * calls {@link SchematicHelper#loadLitematica} to register it in Litematica
     * at the player's current feet position.
     *
     * <p>Each JsonObject must have integer fields {@code x}, {@code y}, {@code z}
     * and a string field {@code block} (e.g. {@code "minecraft:oak_log[axis=y]"}).
     * All coordinates are treated as relative offsets from the origin.</p>
     */
    private static void writeLitematicAndLoad(String name, List<JsonObject> blocks) {
        MinecraftClient mc = MinecraftClient.getInstance();
        if (mc.player == null) {
            addMessage("[System] Join a world before building!");
            return;
        }

        BlockPos origin = mc.player.getBlockPos();

        // Find the bounding box of all blocks
        int minX = 0, minY = 0, minZ = 0;
        int maxX = 0, maxY = 0, maxZ = 0;
        for (JsonObject b : blocks) {
            int x = b.get("x").getAsInt();
            int y = b.get("y").getAsInt();
            int z = b.get("z").getAsInt();
            if (x < minX) minX = x; if (x > maxX) maxX = x;
            if (y < minY) minY = y; if (y > maxY) maxY = y;
            if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
        }

        int sizeX = maxX - minX + 1;
        int sizeY = maxY - minY + 1;
        int sizeZ = maxZ - minZ + 1;

        // Build a palette and index array
        List<String>  palette  = new ArrayList<>();
        int[]         indices  = new int[sizeX * sizeY * sizeZ];
        java.util.Arrays.fill(indices, 0);           // default = air
        palette.add("minecraft:air");

        for (JsonObject b : blocks) {
            int x     = b.get("x").getAsInt() - minX;
            int y     = b.get("y").getAsInt() - minY;
            int z     = b.get("z").getAsInt() - minZ;
            String id = b.get("block").getAsString();
            if (id.equals("minecraft:air")) continue;
            int palIdx = palette.indexOf(id);
            if (palIdx < 0) { palIdx = palette.size(); palette.add(id); }
            int flatIdx = y * sizeZ * sizeX + z * sizeX + x;
            if (flatIdx >= 0 && flatIdx < indices.length) indices[flatIdx] = palIdx;
        }

        // Pack into a .litematic NBT and write to disk, then load
        try {
            int bitsPerEntry = Math.max(2,
                    Integer.SIZE - Integer.numberOfLeadingZeros(palette.size() - 1));
            long[] packed = packBitsForLitematic(indices, bitsPerEntry);

            net.minecraft.nbt.NbtCompound root    = new net.minecraft.nbt.NbtCompound();
            root.putInt("MinecraftDataVersion", 3953);
            root.putInt("Version", 6);

            net.minecraft.nbt.NbtCompound meta = new net.minecraft.nbt.NbtCompound();
            meta.putString("Author", "ClaudeCraft");
            meta.putString("Name", name);
            meta.putLong("TimeCreated", System.currentTimeMillis());
            meta.putLong("TimeModified", System.currentTimeMillis());
            net.minecraft.nbt.NbtCompound encSize = new net.minecraft.nbt.NbtCompound();
            encSize.putInt("x", sizeX); encSize.putInt("y", sizeY); encSize.putInt("z", sizeZ);
            meta.put("EnclosingSize", encSize);
            meta.putInt("TotalBlocks", blocks.size());
            meta.putInt("TotalVolume", sizeX * sizeY * sizeZ);
            root.put("Metadata", meta);

            net.minecraft.nbt.NbtCompound region = new net.minecraft.nbt.NbtCompound();
            net.minecraft.nbt.NbtCompound pos = new net.minecraft.nbt.NbtCompound();
            pos.putInt("x", 0); pos.putInt("y", 0); pos.putInt("z", 0);
            region.put("Position", pos);
            net.minecraft.nbt.NbtCompound sz = new net.minecraft.nbt.NbtCompound();
            sz.putInt("x", sizeX); sz.putInt("y", sizeY); sz.putInt("z", sizeZ);
            region.put("Size", sz);

            net.minecraft.nbt.NbtList paletteNbt = new net.minecraft.nbt.NbtList();
            for (String blockId : palette) {
                // Strip block state properties for the palette entry name
                String paletteName = blockId.contains("[") ? blockId.substring(0, blockId.indexOf('[')) : blockId;
                net.minecraft.nbt.NbtCompound entry = new net.minecraft.nbt.NbtCompound();
                entry.putString("Name", paletteName);
                paletteNbt.add(entry);
            }
            region.put("BlockStatePalette", paletteNbt);
            region.putLongArray("BlockStates", packed);
            region.put("Entities",           new net.minecraft.nbt.NbtList());
            region.put("PendingBlockTicks",   new net.minecraft.nbt.NbtList());
            region.put("PendingFluidTicks",   new net.minecraft.nbt.NbtList());
            region.put("TileEntities",        new net.minecraft.nbt.NbtList());

            net.minecraft.nbt.NbtCompound regions = new net.minecraft.nbt.NbtCompound();
            regions.put(name, region);
            root.put("Regions", regions);

            java.io.File dir  = new java.io.File(mc.runDirectory, "litematics");
            dir.mkdirs();
            java.io.File file = new java.io.File(dir, name + ".litematic");
            net.minecraft.nbt.NbtIo.writeCompressed(root, file.toPath());

            ClaudeCraft.LOGGER.info("Wrote streamed schematic to " + file.getAbsolutePath());
            SchematicHelper.loadLitematica(mc.world, origin, name);

        } catch (Exception e) {
            ClaudeCraft.LOGGER.error("Failed to write streamed schematic", e);
            addMessage("[System] Error writing schematic: " + e.getMessage());
        }
    }

    /** Same bit-packing used by Litematica / SchematicHelper.saveLitematica. */
    private static long[] packBitsForLitematic(int[] indices, int bitsPerEntry) {
        long[] result = new long[(indices.length * bitsPerEntry + 63) / 64];
        for (int i = 0; i < indices.length; i++) {
            int value     = indices[i];
            int bitIndex  = i * bitsPerEntry;
            int longIndex = bitIndex / 64;
            int bitOffset = bitIndex % 64;
            result[longIndex] |= ((long) value) << bitOffset;
            if (bitOffset + bitsPerEntry > 64 && longIndex + 1 < result.length)
                result[longIndex + 1] |= ((long) value) >>> (64 - bitOffset);
        }
        return result;
    }

    private void onSend() {
        String text = inputField != null ? inputField.getText().trim() : "";
        if (text.isEmpty()) return;
        addMessage("You: " + text);
        ensureConnected();
        if (persistentClient != null && persistentClient.isOpen()) {
            persistentClient.send(text);
        } else {
            MinecraftClient.getInstance().execute(() -> {
                if (persistentClient != null && persistentClient.isOpen())
                    persistentClient.send(text);
                else
                    addMessage("[System] Not connected \u2014 start the server first!");
            });
        }
        inputField.setText("");
    }

    private void onBuild() {
        String text = inputField != null ? inputField.getText().trim() : "";
        if (text.isEmpty()) return;
        addMessage("[Build] " + text);
        ensureConnected();
        if (persistentClient != null && persistentClient.isOpen())
            persistentClient.send("[BUILD] " + text);
        else {
            addMessage("[System] Not connected \u2014 start the server first!");
            ensureConnected();
        }
        inputField.setText("");
    }

    // ── Schematic tab actions ────────────────────────────────────────────────
    private void onLoadSchematic() {
        String name = schematicField != null ? schematicField.getText().trim() : "";
        if (name.isEmpty()) {
            addMessage("[System] Enter a schematic name first.");
            activeTab = 0; this.clearAndInit(); return;
        }
        // Strip trailing .litematic if user included it
        if (name.endsWith(".litematic")) name = name.substring(0, name.length() - 10);
        addMessage("[Schematic] Loading: " + name);
        MinecraftClient mc = MinecraftClient.getInstance();
        if (mc.player != null) {
            mc.player.sendMessage(Text.literal("[ClaudeCraft] Loading: " + name), false);
            SchematicHelper.loadLitematica(mc.world, mc.player.getBlockPos(), name);
        } else {
            addMessage("[System] Join a world first!");
        }
        activeTab = 0; this.clearAndInit();
    }

    private void onBuildSchematic() {
        String name = schematicField != null ? schematicField.getText().trim() : "";
        if (name.isEmpty()) {
            addMessage("[System] Enter a schematic name first.");
            return;
        }
        // Send to AI as a build request so server streams BUILD_LAYER packets
        ensureConnected();
        String msg = "Build " + name;
        addMessage("[Build] " + msg);
        if (persistentClient != null && persistentClient.isOpen())
            persistentClient.send("[BUILD] " + msg);
        else
            addMessage("[System] Not connected \u2014 start the server first!");
        activeTab = 0; this.clearAndInit();
    }

    // ── My Files helpers ─────────────────────────────────────────────────────

    /**
     * Returns all .litematic files found in the two standard Minecraft folders:
     *   .minecraft/litematics/   (files written by ClaudeCraft's streaming build)
     *   .minecraft/schematics/   (files placed manually / downloaded)
     * Files are sorted alphabetically within each folder; litematics/ comes first.
     */
    private List<Path> scanLitematicFolders() {
        java.io.File runDir = MinecraftClient.getInstance().runDirectory;
        List<Path> results = new ArrayList<>();
        for (String folderName : new String[]{"litematics", "schematics"}) {
            java.io.File dir = new java.io.File(runDir, folderName);
            if (!dir.exists()) continue;
            java.io.File[] files = dir.listFiles(
                    f -> f.isFile() && f.getName().endsWith(".litematic"));
            if (files == null) continue;
            Arrays.sort(files, Comparator.comparing(java.io.File::getName));
            for (java.io.File f : files) results.add(f.toPath());
        }
        return results;
    }

    /**
     * Load a schematic from an explicit folder path (not from the type-in field).
     * Copies the file into litematics/ if it isn't already there, then calls
     * {@link SchematicHelper#loadLitematica} so Litematica registers it.
     */
    private void onLoadFileSchematic(String stem, Path parentFolder) {
        MinecraftClient mc = MinecraftClient.getInstance();
        java.io.File runDir = mc.runDirectory;

        // Make sure it ends up in litematics/ (SchematicHelper always looks there)
        java.io.File liteDir  = new java.io.File(runDir, "litematics");
        java.io.File srcFile  = new java.io.File(parentFolder.toFile(), stem + ".litematic");
        java.io.File destFile = new java.io.File(liteDir, stem + ".litematic");

        try {
            if (!destFile.exists()) {
                liteDir.mkdirs();
                Files.copy(srcFile.toPath(), destFile.toPath());
            }
        } catch (Exception e) {
            ClaudeCraft.LOGGER.warn("Could not copy schematic to litematics/: " + e.getMessage());
        }

        addMessage("[Schematic] Loading: " + stem);
        if (mc.player != null) {
            mc.player.sendMessage(
                Text.literal("§a[ClaudeCraft] Loading: " + stem), false);
            SchematicHelper.loadLitematica(mc.world, mc.player.getBlockPos(), stem);
        } else {
            addMessage("[System] Join a world first!");
        }
        activeTab = 0; this.clearAndInit();
    }

    public static void addMessage(String msg) {
        if (allSessions.isEmpty()) newSession();
        List<String> msgs = currentMessages();
        msgs.add(msg);
        while (msgs.size() > MAX_HISTORY) msgs.remove(0);
        saveHistory();
    }

    // ── Rename commit ────────────────────────────────────────────────────────
    private void commitRename() {
        if (renameField == null || renamingSession < 0 ||
                renamingSession >= allSessions.size()) return;
        String newName = renameField.getText().trim();
        if (!newName.isEmpty()) {
            allSessions.get(renamingSession).name = newName;
            saveHistory();
        }
        renamingSession = -1;
        this.clearAndInit();
    }

    // ── Input ────────────────────────────────────────────────────────────────
    @Override
    public boolean keyPressed(KeyInput input) {
        int key = input.key();

        // Rename field active: Enter = confirm, Escape = cancel
        if (renameField != null && renameField.isFocused()) {
            if (key == GLFW.GLFW_KEY_ENTER || key == GLFW.GLFW_KEY_KP_ENTER) {
                commitRename(); return true;
            }
            if (key == GLFW.GLFW_KEY_ESCAPE) {
                renamingSession = -1;
                this.clearAndInit(); return true;
            }
            return super.keyPressed(input);
        }

        // Schematic tab: Enter = load
        if (activeTab == 1 && schematicField != null && schematicField.isFocused()) {
            if (key == GLFW.GLFW_KEY_ENTER || key == GLFW.GLFW_KEY_KP_ENTER) {
                onLoadSchematic(); return true;
            }
        }

        if (activeTab == 0 && (key == GLFW.GLFW_KEY_ENTER || key == GLFW.GLFW_KEY_KP_ENTER)) {
            onSend(); return true;
        }
        return super.keyPressed(input);
    }

    @Override public boolean shouldCloseOnEsc() { return true; }
    @Override public boolean shouldPause()       { return false; }

    @Override
    public void renderBackground(DrawContext ctx, int mx, int my, float delta) {
        // transparent — world shows through
    }

    // ── Render ───────────────────────────────────────────────────────────────
    @Override
    public void render(DrawContext ctx, int mouseX, int mouseY, float delta) {
        int sl  = left();
        int cl  = chatLeft();
        int pt  = top();
        int pb  = pt + TOTAL_H;
        int sr  = cl;
        int cr  = cl + CHAT_W;

        // ── Sidebar background
        ctx.fill(sl, pt, sr, pb, C_SIDEBAR_BG);

        // ── Sidebar header "Chats"
        ctx.drawText(this.textRenderer, "Chats", sl + PAD, pt + 4, C_HDR, false);
        ctx.fill(sl, pt + 14, sr, pt + 15, C_DIVIDER);

        // ── Row highlights (draw before widgets so they sit behind button text)
        int newBtnY   = pt + 18;
        int rowStartY = newBtnY + BTN_H + 4;
        int labelW    = SIDEBAR_W - PAD * 2 - ICON_W - ICON_GAP - ICON_W - ICON_GAP;

        // Active row
        if (!allSessions.isEmpty() && renamingSession != activeSession) {
            int rowIdx = allSessions.size() - 1 - activeSession;
            int rowY   = rowStartY + rowIdx * (ROW_H + 2);
            if (rowY + ROW_H <= pb - PAD)
                ctx.fill(sl + PAD - 2, rowY - 1, sr - PAD + 2, rowY + ROW_H + 1, C_ROW_ACT);
        }
        // Rename row
        if (renamingSession >= 0 && renamingSession < allSessions.size()) {
            int rowIdx = allSessions.size() - 1 - renamingSession;
            int rowY   = rowStartY + rowIdx * (ROW_H + 2);
            ctx.fill(sl + PAD - 2, rowY - 1, sr - PAD + 2, rowY + ROW_H + 1, C_RENAME_BG);
        }

        // ── Vertical divider
        ctx.fill(sr, pt, sr + 1, pb, C_DIVIDER);

        // ── Chat panel background
        ctx.fill(cl, pt, cr, pb, C_CHAT_BG);

        // ── Tab bar background + active highlight
        int tabW = (CHAT_W - PAD * 2) / 3;
        ctx.fill(cl, pt, cr, pt + 18, (int) 0xEE111118);
        // Active tab underline (purple bar under the active tab)
        int ulX = cl + PAD + activeTab * tabW;
        ctx.fill(ulX, pt + 15, ulX + tabW - 2, pt + 17, C_AI);

        // ── Connection dot (top-right)
        boolean connected = persistentClient != null && persistentClient.isOpen();
        ctx.drawText(this.textRenderer, "\u25CF", cr - 14, pt + 5,
                connected ? 0xFF55FF55 : 0xFFFF5555, true);

        if (activeTab == 0) {
            // ── CHAT PANEL ───────────────────────────────────────────────────

            // ── Input area divider
            int btnY   = pb - BOT_PAD - BTN_H;
            int inputY = btnY - PAD - INPUT_H;
            ctx.fill(cl + PAD, inputY - 4, cr - PAD, inputY - 3, C_DIVIDER);

            // ── Chat history
            int textTop    = pt + 22;
            int textBottom = inputY - 6;
            int maxTextW   = CHAT_W - PAD * 2;

            List<String[]> lines = new ArrayList<>();
            for (String msg : currentMessages()) {
                String prefix = msg.startsWith("AI: ")  ? "AI"  :
                                msg.startsWith("You: ") ? "You" : "Sys";
                List<String> wrapped = wrapText(msg, maxTextW);
                for (int i = 0; i < wrapped.size(); i++)
                    lines.add(new String[]{ i == 0 ? prefix : "", wrapped.get(i) });
            }

            int maxLines = (textBottom - textTop) / LINE_H;
            int start    = Math.max(0, lines.size() - maxLines);
            int y = textTop;
            for (int i = start; i < lines.size(); i++) {
                String[] e = lines.get(i);
                int color = "AI".equals(e[0])  ? C_AI   :
                            "You".equals(e[0]) ? C_WHITE : C_SYS;
                ctx.drawText(this.textRenderer, e[1], cl + PAD, y, color, true);
                y += LINE_H;
            }

        } else if (activeTab == 1) {
            // ── SCHEMATIC PANEL ──────────────────────────────────────────────
            int tx = cl + PAD;
            int ty = pt + 22;
            ctx.drawText(this.textRenderer, "Load a Schematic", tx, ty, C_AI, false);
            ctx.drawText(this.textRenderer, "Paste the schematic name below.", tx, ty + 12, C_SYS, false);
            ctx.drawText(this.textRenderer, "(without .litematic extension)", tx, ty + 22, C_SYS, false);
            ctx.drawText(this.textRenderer, "Load  \u2192 places at your feet via Litematica", tx, ty + 36 + INPUT_H + 6 + BTN_H + 8, C_SYS, false);
            ctx.drawText(this.textRenderer, "Build \u2192 streams layers from AI server",       tx, ty + 36 + INPUT_H + 6 + BTN_H + 20, C_SYS, false);

        } else {
            // ── MY FILES PANEL ───────────────────────────────────────────────
            int tx = cl + PAD;
            int ty = pt + 22;
            ctx.drawText(this.textRenderer, "Your .litematic files", tx, ty - 2, C_AI, false);
            ctx.fill(cl + PAD, ty + 8, cr - PAD, ty + 9, C_DIVIDER);

            // Show folder labels as faint headers between groups
            List<Path> files = scanLitematicFolders();
            if (files.isEmpty()) {
                ctx.drawText(this.textRenderer, "No .litematic files found.", tx, ty + 14, C_SYS, false);
                ctx.drawText(this.textRenderer, "Place files in:", tx, ty + 26, C_SYS, false);
                ctx.drawText(this.textRenderer, "  .minecraft/litematics/", tx, ty + 38, 0xFF6688AA, false);
                ctx.drawText(this.textRenderer, "  .minecraft/schematics/", tx, ty + 50, 0xFF6688AA, false);
            }
            // (buttons for each file are added in init())
        }

        // ── Widgets (buttons, input field, rename field, schematic field)
        super.render(ctx, mouseX, mouseY, delta);
        if (inputField != null) inputField.render(ctx, mouseX, mouseY, delta);
    }

    // ── Helpers ──────────────────────────────────────────────────────────────
    private String truncate(String text, int maxWidth) {
        String t = text;
        while (t.length() > 1 && this.textRenderer.getWidth(t + "..") > maxWidth)
            t = t.substring(0, t.length() - 1);
        return t.length() < text.length() ? t + ".." : t;
    }

    private List<String> wrapText(String text, int maxWidth) {
        List<String> lines = new ArrayList<>();
        String[] words = text.split(" ", -1);
        StringBuilder cur = new StringBuilder();
        for (String word : words) {
            String candidate = cur.length() > 0 ? cur + " " + word : word;
            if (this.textRenderer.getWidth(candidate) > maxWidth && cur.length() > 0) {
                lines.add(cur.toString());
                cur = new StringBuilder(word);
            } else {
                cur = new StringBuilder(candidate);
            }
        }
        if (cur.length() > 0) lines.add(cur.toString());
        if (lines.isEmpty()) lines.add("");
        return lines;
    }
}
