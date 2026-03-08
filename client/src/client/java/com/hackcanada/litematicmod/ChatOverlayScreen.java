package com.hackcanada.litematicmod;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.reflect.TypeToken;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.TextFieldWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.text.Text;
import org.lwjgl.glfw.GLFW;

import java.io.*;
import java.lang.reflect.Type;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.file.*;
import java.text.SimpleDateFormat;
import java.util.*;

public class ChatOverlayScreen extends Screen {

    // ── Layout ───────────────────────────────────────────────────────────────────
    private static final int PANEL_WIDTH   = 340;
    private static final int PANEL_HEIGHT  = 280;
    private static final int PAD           = 10;
    private static final int INPUT_HEIGHT  = 20;
    private static final int BTN_HEIGHT    = 20;
    private static final int BTN_WIDTH     = (PANEL_WIDTH - PAD * 2 - 4) / 2;
    private static final int LINE_HEIGHT   = 12;
    private static final int MAX_HISTORY   = 200;
    private static final int TAB_HEIGHT    = 16;
    private static final int TAB_WIDTH     = 80;
    private static final int MAX_SESSIONS  = 5;

    // Colors
    private static final int COLOR_YOU     = 0xFFFFFFFF;
    private static final int COLOR_AI      = 0xFFCC77FF;
    private static final int COLOR_SYS     = 0xFFAAAAAA;
    private static final int COLOR_BG      = (int) 0xDD101010;
    private static final int COLOR_DIVIDER = (int) 0x88FFFFFF;
    private static final int COLOR_TAB_ACT = (int) 0xFF333355;
    private static final int COLOR_TAB_IN  = (int) 0xFF1A1A2A;
    private static final int COLOR_TAB_TXT = 0xFFCCCCCC;
    private static final int COLOR_NEW_BTN = (int) 0xFF224422;

    // ── Persistence file ─────────────────────────────────────────────────────────
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static Path historyFile() {
        return MinecraftClient.getInstance().runDirectory.toPath()
                .resolve("claudecraft_history.json");
    }

    // ── Session model ─────────────────────────────────────────────────────────────
    /** One conversation session. */
    static class Session {
        String name;
        List<String> messages = new ArrayList<>();
        Session(String name) { this.name = name; }
    }

    // ── Persistent state ─────────────────────────────────────────────────────────
    static List<Session>    allSessions   = new ArrayList<>();
    static int              activeSession = 0;   // index into allSessions
    private static BackendClient persistentClient;
    private static long lastConnectAttemptMs = 0;
    private static final long RECONNECT_COOLDOWN_MS = 5000;

    // ── Per-instance widgets ─────────────────────────────────────────────────────
    private TextFieldWidget inputField;

    public ChatOverlayScreen() {
        super(Text.literal("AI Chat"));
    }

    // ── Layout helpers ───────────────────────────────────────────────────────────
    private int panelLeft() { return (this.width  - PANEL_WIDTH)  / 2; }
    private int panelTop()  { return (this.height - PANEL_HEIGHT) / 2; }

    // ── Convenience: current session's message list ──────────────────────────────
    private static List<String> currentMessages() {
        if (allSessions.isEmpty()) newSession();
        return allSessions.get(activeSession).messages;
    }

    // ── Disk I/O ─────────────────────────────────────────────────────────────────
    static void loadHistory() {
        Path f = historyFile();
        if (!Files.exists(f)) { newSession(); return; }
        try (Reader r = Files.newBufferedReader(f)) {
            Type listType = new TypeToken<List<Session>>(){}.getType();
            List<Session> loaded = GSON.fromJson(r, listType);
            if (loaded != null && !loaded.isEmpty()) {
                allSessions = loaded;
                activeSession = allSessions.size() - 1; // open most recent
                return;
            }
        } catch (Exception e) {
            Litemod.LOGGER.warn("Could not load chat history: {}", e.getMessage());
        }
        newSession();
    }

    static void saveHistory() {
        try {
            Path f = historyFile();
            Files.createDirectories(f.getParent());
            try (Writer w = Files.newBufferedWriter(f)) {
                GSON.toJson(allSessions, w);
            }
        } catch (Exception e) {
            Litemod.LOGGER.warn("Could not save chat history: {}", e.getMessage());
        }
    }

    // ── Session management ───────────────────────────────────────────────────────
    static void newSession() {
        String name = "Chat " + new SimpleDateFormat("MM/dd HH:mm").format(new Date());
        allSessions.add(new Session(name));
        activeSession = allSessions.size() - 1;
        // Keep at most MAX_SESSIONS (drop oldest)
        while (allSessions.size() > MAX_SESSIONS) allSessions.remove(0);
        if (activeSession >= allSessions.size()) activeSession = allSessions.size() - 1;
        saveHistory();
    }

    // ── Lifecycle ────────────────────────────────────────────────────────────────
    @Override
    protected void init() {
        super.init();

        if (allSessions.isEmpty()) loadHistory();
        if (currentMessages().isEmpty()) {
            currentMessages().add("[System] Type a message and press Send or Enter.");
            currentMessages().add("[System] Use Build to ask the AI to build something.");
        }

        ensureConnected();

        int pl = panelLeft();
        int pt = panelTop();
        int btnY   = pt + PANEL_HEIGHT - PAD - BTN_HEIGHT;
        int inputY = btnY - PAD - INPUT_HEIGHT;

        inputField = new TextFieldWidget(
                this.textRenderer, pl + PAD, inputY,
                PANEL_WIDTH - PAD * 2, INPUT_HEIGHT,
                Text.literal("Ask AI..."));
        inputField.setMaxLength(512);
        inputField.setDrawsBackground(true);
        inputField.setPlaceholder(Text.literal("Ask AI..."));
        this.addSelectableChild(inputField);
        this.setInitialFocus(inputField);

        // Send / Build buttons
        this.addDrawableChild(ButtonWidget.builder(Text.literal("Send"), btn -> onSend())
                .dimensions(pl + PAD, btnY, BTN_WIDTH, BTN_HEIGHT).build());
        this.addDrawableChild(ButtonWidget.builder(Text.literal("Build"), btn -> onBuild())
                .dimensions(pl + PAD + BTN_WIDTH + 4, btnY, BTN_WIDTH, BTN_HEIGHT).build());

        // "New Chat" button — top-right of panel
        this.addDrawableChild(ButtonWidget.builder(Text.literal("+ New"), btn -> {
            newSession();
            this.clearAndInit();
        }).dimensions(pl + PANEL_WIDTH - 46, pt + 2, 44, TAB_HEIGHT - 2).build());

        // Tab buttons — one per session
        int tabsAreaWidth = PANEL_WIDTH - 50;
        int tabW = Math.min(TAB_WIDTH, tabsAreaWidth / Math.max(1, allSessions.size()));
        for (int i = 0; i < allSessions.size(); i++) {
            final int idx = i;
            String label = allSessions.get(i).name;
            // Truncate label to fit tab
            while (label.length() > 3 && this.textRenderer.getWidth(label) > tabW - 6)
                label = label.substring(0, label.length() - 1);
            int tabBgColor = (i == activeSession) ? COLOR_TAB_ACT : COLOR_TAB_IN;
            // Use a small transparent-ish button per tab
            ButtonWidget tabBtn = ButtonWidget.builder(Text.literal(label), btn -> {
                activeSession = idx;
                ChatOverlayScreen.this.clearAndInit();
            }).dimensions(pl + i * (tabW + 2), pt + 1, tabW, TAB_HEIGHT - 2).build();
            this.addDrawableChild(tabBtn);
        }
    }

    // ── Connection ───────────────────────────────────────────────────────────────
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
            Litemod.LOGGER.error("Invalid WebSocket URI", e);
        }
    }

    // ── Incoming messages ────────────────────────────────────────────────────────
    private static void handleIncomingMessage(String message) {
        MinecraftClient.getInstance().execute(() -> {
            if (message.startsWith("LOAD_SCHEMATIC ")) {
                String filename = message.substring("LOAD_SCHEMATIC ".length()).trim();
                addMessage("AI: Loading schematic: " + filename);
                MinecraftClient mc = MinecraftClient.getInstance();
                if (mc.player != null) {
                    mc.player.sendMessage(Text.literal("[ClaudeCraft] Loading: " + filename), false);
                    LitematicaHelper.loadLitematica(mc.world, mc.player.getBlockPos(), filename);
                }
            } else {
                addMessage("AI: " + message);
            }
        });
    }

    // ── Button / Enter handlers ──────────────────────────────────────────────────
    private void onSend() {
        String text = inputField != null ? inputField.getText().trim() : "";
        if (text.isEmpty()) return;
        addMessage("You: " + text);
        ensureConnected();
        if (persistentClient != null && persistentClient.isOpen()) {
            persistentClient.send(text);
        } else {
            MinecraftClient.getInstance().execute(() -> {
                if (persistentClient != null && persistentClient.isOpen()) {
                    persistentClient.send(text);
                } else {
                    addMessage("[System] Not connected — start the server first!");
                }
            });
        }
        inputField.setText("");
    }

    private void onBuild() {
        String text = inputField != null ? inputField.getText().trim() : "";
        if (text.isEmpty()) return;
        addMessage("[Build] " + text);
        ensureConnected();
        if (persistentClient != null && persistentClient.isOpen()) {
            persistentClient.send("[BUILD] " + text);
        } else {
            addMessage("[System] Not connected — start the server first!");
            ensureConnected();
        }
        inputField.setText("");
    }

    public static void addMessage(String msg) {
        if (allSessions.isEmpty()) newSession();
        List<String> msgs = currentMessages();
        msgs.add(msg);
        while (msgs.size() > MAX_HISTORY) msgs.remove(0);
        saveHistory();
    }

    // ── Input ────────────────────────────────────────────────────────────────────
    @Override
    public boolean keyPressed(KeyInput input) {
        int keyCode = input.key();
        if (keyCode == GLFW.GLFW_KEY_ENTER || keyCode == GLFW.GLFW_KEY_KP_ENTER) {
            onSend(); return true;
        }
        return super.keyPressed(input);
    }

    @Override public boolean shouldCloseOnEsc() { return true; }
    @Override public boolean shouldPause()       { return false; }

    @Override
    public void renderBackground(DrawContext context, int mouseX, int mouseY, float delta) {
        // empty — overlay over game world
    }

    // ── Rendering ────────────────────────────────────────────────────────────────
    @Override
    public void render(DrawContext context, int mouseX, int mouseY, float delta) {
        int pl = panelLeft();
        int pt = panelTop();
        int pr = pl + PANEL_WIDTH;
        int pb = pt + PANEL_HEIGHT;

        // ── Panel background
        context.fill(pl, pt, pr, pb, COLOR_BG);

        // Highlight active tab background (tab buttons are drawn by super.render below)
        int tabsAreaWidth = PANEL_WIDTH - 50;
        int tabW = Math.min(TAB_WIDTH, tabsAreaWidth / Math.max(1, allSessions.size()));
        int activeTx = pl + activeSession * (tabW + 2);
        context.fill(activeTx, pt + 1, activeTx + tabW, pt + TAB_HEIGHT - 1, COLOR_TAB_ACT);

        // Divider under tabs
        context.fill(pl, pt + TAB_HEIGHT + 2, pr, pt + TAB_HEIGHT + 3, COLOR_DIVIDER);

        // ── Bottom widgets Y positions
        int btnY   = pb - PAD - BTN_HEIGHT;
        int inputY = btnY - PAD - INPUT_HEIGHT;

        // ── Divider above input area
        context.fill(pl + PAD, inputY - 4, pr - PAD, inputY - 3, COLOR_DIVIDER);

        // ── Chat history ─────────────────────────────────────────────────────────
        int textAreaTop    = pt + TAB_HEIGHT + 6;
        int textAreaBottom = inputY - 8;
        int maxTextWidth   = PANEL_WIDTH - PAD * 2;

        List<String[]> wrappedLines = new ArrayList<>();
        for (String msg : currentMessages()) {
            String prefix = msg.startsWith("AI: ") ? "AI" :
                            msg.startsWith("You: ") ? "You" : "Sys";
            List<String> wrapped = wrapText(msg, maxTextWidth);
            for (int i = 0; i < wrapped.size(); i++) {
                wrappedLines.add(new String[]{ i == 0 ? prefix : "", wrapped.get(i) });
            }
        }

        int maxLines = (textAreaBottom - textAreaTop) / LINE_HEIGHT;
        int startIdx = Math.max(0, wrappedLines.size() - maxLines);
        int y = textAreaTop;
        for (int i = startIdx; i < wrappedLines.size(); i++) {
            String[] entry = wrappedLines.get(i);
            int color = "AI".equals(entry[0])  ? COLOR_AI  :
                        "You".equals(entry[0]) ? COLOR_YOU : COLOR_SYS;
            context.drawText(this.textRenderer, entry[1], pl + PAD, y, color, true);
            y += LINE_HEIGHT;
        }

        // ── Widgets (buttons + input)
        super.render(context, mouseX, mouseY, delta);
        inputField.render(context, mouseX, mouseY, delta);

        // ── Connection dot
        boolean connected = persistentClient != null && persistentClient.isOpen();
        context.drawText(this.textRenderer, "●", pr - 12, pt + TAB_HEIGHT + 5,
                connected ? 0xFF55FF55 : 0xFFFF5555, true);
    }

    // ── Word wrap ────────────────────────────────────────────────────────────────
    private List<String> wrapText(String text, int maxWidth) {
        List<String> lines = new ArrayList<>();
        String[] words = text.split(" ", -1);
        StringBuilder current = new StringBuilder();
        for (String word : words) {
            String candidate = current.length() > 0 ? current + " " + word : word;
            if (this.textRenderer.getWidth(candidate) > maxWidth && current.length() > 0) {
                lines.add(current.toString());
                current = new StringBuilder(word);
            } else {
                current = new StringBuilder(candidate);
            }
        }
        if (current.length() > 0) lines.add(current.toString());
        if (lines.isEmpty()) lines.add("");
        return lines;
    }
}
