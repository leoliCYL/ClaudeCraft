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

    // ── Layout — ChatGPT style: sidebar left + chat right ──────────────────
    private static final int SIDEBAR_W    = 115;
    private static final int CHAT_W       = 280;
    private static final int TOTAL_W      = SIDEBAR_W + CHAT_W;
    private static final int TOTAL_H      = 260;
    private static final int PAD          = 8;
    private static final int INPUT_H      = 20;
    private static final int BTN_H        = 20;
    private static final int BTN_W        = (CHAT_W - PAD * 2 - 4) / 2;
    private static final int LINE_H       = 12;
    private static final int MAX_HISTORY  = 200;
    private static final int MAX_SESSIONS = 8;
    private static final int ROW_H        = 22;
    private static final int RENAME_BTN_W = 16;

    // Colors
    private static final int C_WHITE      = 0xFFFFFFFF;
    private static final int C_AI         = 0xFFCC77FF;
    private static final int C_SYS        = 0xFFAAAAAA;
    private static final int C_CHAT_BG    = (int) 0xEE0D0D14;
    private static final int C_SIDEBAR_BG = (int) 0xEE07070E;
    private static final int C_DIVIDER    = (int) 0x55FFFFFF;
    private static final int C_ROW_ACT    = (int) 0xFF1E3A5F;
    private static final int C_HDR        = 0xFF8888AA;
    private static final int C_RENAME_BG  = (int) 0xFF0D2040;

    // ── Persistence ─────────────────────────────────────────────────────────
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    private static Path historyFile() {
        return MinecraftClient.getInstance().runDirectory.toPath()
                .resolve("claudecraft_history.json");
    }

    static class Session {
        String name;
        List<String> messages = new ArrayList<>();
        Session(String name) { this.name = name; }
    }

    // ── Persistent state ─────────────────────────────────────────────────────
    static List<Session> allSessions   = new ArrayList<>();
    static int           activeSession = 0;
    private static BackendClient persistentClient;
    private static long lastConnectAttemptMs = 0;
    private static final long RECONNECT_COOLDOWN_MS = 5000;

    // ── Per-instance widgets ─────────────────────────────────────────────────
    private TextFieldWidget inputField;

    /** Index of the session currently being renamed, -1 = none. */
    private int renamingSession = -1;
    private TextFieldWidget renameField;

    public ChatOverlayScreen() { super(Text.literal("AI Chat")); }

    // ── Layout helpers ───────────────────────────────────────────────────────
    private int left()     { return (this.width  - TOTAL_W) / 2; }
    private int top()      { return (this.height - TOTAL_H) / 2 + 20; }
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
            Type t = new TypeToken<List<Session>>(){}.getType();
            List<Session> loaded = GSON.fromJson(r, t);
            if (loaded != null && !loaded.isEmpty()) {
                allSessions   = loaded;
                activeSession = allSessions.size() - 1;
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

    static void newSession() {
        String name = new SimpleDateFormat("MM/dd HH:mm").format(new Date());
        allSessions.add(new Session(name));
        activeSession = allSessions.size() - 1;
        while (allSessions.size() > MAX_SESSIONS) allSessions.remove(0);
        if (activeSession >= allSessions.size()) activeSession = allSessions.size() - 1;
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
        int btnY   = pb  - PAD - BTN_H;
        int inputY = btnY - PAD - INPUT_H;

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
        this.addDrawableChild(ButtonWidget.builder(Text.literal("Send"), btn -> onSend())
                .dimensions(cl + PAD, btnY, BTN_W, BTN_H).build());
        this.addDrawableChild(ButtonWidget.builder(Text.literal("Build"), btn -> onBuild())
                .dimensions(cl + PAD + BTN_W + 4, btnY, BTN_W, BTN_H).build());

        // ── "+ New Chat" button
        this.addDrawableChild(ButtonWidget.builder(Text.literal("+ New Chat"), btn -> {
            renamingSession = -1;
            newSession();
            this.clearAndInit();
        }).dimensions(sl + PAD, pt + PAD, SIDEBAR_W - PAD * 2, BTN_H).build());

        // ── Session rows (newest first)
        int rowStartY = pt + PAD + BTN_H + 6;
        for (int i = allSessions.size() - 1; i >= 0; i--) {
            final int idx = i;
            int rowY = rowStartY + (allSessions.size() - 1 - i) * (ROW_H + 2);
            if (rowY + ROW_H > pb - PAD) break;

            int labelW = SIDEBAR_W - PAD * 2 - RENAME_BTN_W - 2;
            String label = truncate(allSessions.get(i).name, labelW);
            this.addDrawableChild(ButtonWidget.builder(Text.literal(label), btn -> {
                renamingSession = -1;
                activeSession   = idx;
                this.clearAndInit();
            }).dimensions(sl + PAD, rowY, labelW, ROW_H).build());

            // ✎ rename button
            this.addDrawableChild(ButtonWidget.builder(Text.literal("\u270E"), btn -> {
                renamingSession = idx;
                this.clearAndInit();
            }).dimensions(sl + PAD + labelW + 2, rowY, RENAME_BTN_W, ROW_H).build());
        }

        // ── Rename inline text field
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
            this.addSelectableChild(renameField);
            this.setInitialFocus(renameField);
        } else {
            renameField = null;
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
            Litemod.LOGGER.error("Invalid WebSocket URI", e);
        }
    }

    // ── Messages ─────────────────────────────────────────────────────────────
    private static void handleIncomingMessage(String message) {
        MinecraftClient.getInstance().execute(() -> {
            if (message.startsWith("LOAD_SCHEMATIC ")) {
                String fn = message.substring("LOAD_SCHEMATIC ".length()).trim();
                addMessage("AI: Loading schematic: " + fn);
                MinecraftClient mc = MinecraftClient.getInstance();
                if (mc.player != null) {
                    mc.player.sendMessage(Text.literal("[ClaudeCraft] Loading: " + fn), false);
                    LitematicaHelper.loadLitematica(mc.world, mc.player.getBlockPos(), fn);
                }
            } else {
                addMessage("AI: " + message);
            }
        });
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

        // Rename field: Enter confirms, Escape cancels
        if (renameField != null && getFocused() == renameField) {
            if (key == GLFW.GLFW_KEY_ENTER || key == GLFW.GLFW_KEY_KP_ENTER) {
                commitRename(); return true;
            }
            if (key == GLFW.GLFW_KEY_ESCAPE) {
                renamingSession = -1;
                this.clearAndInit(); return true;
            }
            return super.keyPressed(input);
        }

        if (key == GLFW.GLFW_KEY_ENTER || key == GLFW.GLFW_KEY_KP_ENTER) {
            onSend(); return true;
        }
        return super.keyPressed(input);
    }

    @Override public boolean shouldCloseOnEsc() { return true; }
    @Override public boolean shouldPause()       { return false; }

    @Override
    public void renderBackground(DrawContext ctx, int mx, int my, float delta) {
        // transparent
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

        // Sidebar background
        ctx.fill(sl, pt, sr, pb, C_SIDEBAR_BG);

        // Sidebar header
        ctx.drawText(this.textRenderer, "Conversations", sl + PAD, pt + 4, C_HDR, false);
        ctx.fill(sl, pt + 14, sr, pt + 15, C_DIVIDER);

        // Active session highlight
        int rowStartY = pt + PAD + BTN_H + 6;
        if (!allSessions.isEmpty() && renamingSession != activeSession) {
            int rowIdx = allSessions.size() - 1 - activeSession;
            int rowY   = rowStartY + rowIdx * (ROW_H + 2);
            if (rowY + ROW_H <= pb - PAD)
                ctx.fill(sl + PAD - 2, rowY - 1, sr - PAD + 2, rowY + ROW_H + 1, C_ROW_ACT);
        }

        // Rename row highlight
        if (renamingSession >= 0 && renamingSession < allSessions.size()) {
            int rowIdx = allSessions.size() - 1 - renamingSession;
            int rowY   = rowStartY + rowIdx * (ROW_H + 2);
            ctx.fill(sl + PAD - 2, rowY - 1, sr - PAD + 2, rowY + ROW_H + 1, C_RENAME_BG);
        }

        // Vertical divider
        ctx.fill(sr, pt, sr + 1, pb, C_DIVIDER);

        // Chat panel background
        ctx.fill(cl, pt, cr, pb, C_CHAT_BG);

        // Chat header bar
        ctx.fill(cl, pt, cr, pt + 18, (int) 0xEE111118);
        String hdrName = allSessions.isEmpty() ? "New Chat" : allSessions.get(activeSession).name;
        ctx.drawText(this.textRenderer, hdrName, cl + PAD, pt + 5, C_WHITE, false);

        // Connection dot
        boolean connected = persistentClient != null && persistentClient.isOpen();
        ctx.drawText(this.textRenderer, "\u25CF", cr - 14, pt + 5,
                connected ? 0xFF55FF55 : 0xFFFF5555, true);

        // Input area divider
        int btnY   = pb - PAD - BTN_H;
        int inputY = btnY - PAD - INPUT_H;
        ctx.fill(cl + PAD, inputY - 4, cr - PAD, inputY - 3, C_DIVIDER);

        // Chat history
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
            int color = "AI".equals(e[0])  ? C_AI    :
                        "You".equals(e[0]) ? C_WHITE  : C_SYS;
            ctx.drawText(this.textRenderer, e[1], cl + PAD, y, color, true);
            y += LINE_H;
        }

        // Widgets
        super.render(ctx, mouseX, mouseY, delta);
        inputField.render(ctx, mouseX, mouseY, delta);
        if (renameField != null) renameField.render(ctx, mouseX, mouseY, delta);
    }

    // ── Helpers ──────────────────────────────────────────────────────────────
    private String truncate(String text, int maxWidth) {
        String t = text;
        while (t.length() > 1 && this.textRenderer.getWidth(t + "...") > maxWidth)
            t = t.substring(0, t.length() - 1);
        return t.length() < text.length() ? t + "..." : t;
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
