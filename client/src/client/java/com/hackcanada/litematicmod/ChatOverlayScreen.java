package com.hackcanada.litematicmod;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.TextFieldWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.text.Text;
import org.lwjgl.glfw.GLFW;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.ArrayList;
import java.util.List;

public class ChatOverlayScreen extends Screen {

    // ── Layout ───────────────────────────────────────────────────────────────────
    private static final int PANEL_WIDTH  = 320;
    private static final int PANEL_HEIGHT = 260;
    private static final int PAD          = 10;
    private static final int INPUT_HEIGHT = 20;
    private static final int BTN_HEIGHT   = 20;
    private static final int BTN_WIDTH    = (PANEL_WIDTH - PAD * 2 - 4) / 2;
    private static final int LINE_HEIGHT  = 12;
    private static final int MAX_HISTORY  = 100;

    // Colors
    private static final int COLOR_YOU    = 0xFFFFFFFF; // white
    private static final int COLOR_AI     = 0xFFCC77FF; // purple
    private static final int COLOR_SYS    = 0xFFAAAAAA; // grey
    private static final int COLOR_BG     = (int) 0xDD101010; // near-black panel
    private static final int COLOR_DIVIDER= (int) 0x88FFFFFF; // translucent white

    // ── Persistent state (survives screen re-opens) ──────────────────────────────
    static final List<String> persistentHistory = new ArrayList<>();
    private static BackendClient persistentClient;
    private static long lastConnectAttemptMs = 0;
    private static final long RECONNECT_COOLDOWN_MS = 5000; // 5 s between attempts

    // ── Per-instance widgets ─────────────────────────────────────────────────────
    private TextFieldWidget inputField;

    public ChatOverlayScreen() {
        super(Text.literal("AI Chat"));
    }

    // ── Layout helpers ────────────────────────────────────────────────────────────

    /** Top-left X of the centered panel. */
    private int panelLeft() { return (this.width  - PANEL_WIDTH)  / 2; }
    /** Top-left Y of the centered panel. */
    private int panelTop()  { return (this.height - PANEL_HEIGHT) / 2; }

    // ── Lifecycle ────────────────────────────────────────────────────────────────

    @Override
    protected void init() {
        super.init();

        if (persistentHistory.isEmpty()) {
            persistentHistory.add("Type a message and press Send!");
            persistentHistory.add("Use Build to ask AI to build.");
        }

        ensureConnected();

        int pl = panelLeft();
        int pt = panelTop();

        // Input field — bottom of panel (above the buttons)
        int btnY   = pt + PANEL_HEIGHT - PAD - BTN_HEIGHT;
        int inputY = btnY - PAD - INPUT_HEIGHT;

        inputField = new TextFieldWidget(
                this.textRenderer,
                pl + PAD, inputY,
                PANEL_WIDTH - PAD * 2, INPUT_HEIGHT,
                Text.literal("Ask AI..."));
        inputField.setMaxLength(512);
        inputField.setDrawsBackground(true);
        inputField.setPlaceholder(Text.literal("Ask AI..."));
        this.addSelectableChild(inputField);
        this.setInitialFocus(inputField);

        // Send button (left)
        this.addDrawableChild(ButtonWidget.builder(Text.literal("Send"), btn -> onSend())
                .dimensions(pl + PAD, btnY, BTN_WIDTH, BTN_HEIGHT)
                .build());

        // Build button (right)
        this.addDrawableChild(ButtonWidget.builder(Text.literal("Build"), btn -> onBuild())
                .dimensions(pl + PAD + BTN_WIDTH + 4, btnY, BTN_WIDTH, BTN_HEIGHT)
                .build());
    }

    // ── Connection ───────────────────────────────────────────────────────────────

    private void ensureConnected() {
        if (persistentClient != null && persistentClient.isOpen()) return;
        if (persistentClient != null &&
                persistentClient.getReadyState() == org.java_websocket.enums.ReadyState.CLOSING) return;
        // Rate-limit reconnect attempts to avoid spawning a new thread every frame
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

    // ── Incoming message handler (static so it works across screen re-opens) ────

    private static void handleIncomingMessage(String message) {
        MinecraftClient.getInstance().execute(() -> {
            if (message.startsWith("LOAD_SCHEMATIC ")) {
                String filename = message.substring("LOAD_SCHEMATIC ".length()).trim();
                addMessage("AI: Loading schematic: " + filename);
                MinecraftClient mc = MinecraftClient.getInstance();
                if (mc.player != null) {
                    mc.player.sendMessage(
                            Text.literal("[ClaudeCraft] Loading: " + filename), false);
                    LitematicaHelper.loadLitematica(mc.world, mc.player.getBlockPos(), filename);
                }
            } else {
                addMessage("AI: " + message);
            }
        });
    }

    // ── Button / Enter handlers ──────────────────────────────────────────────────

    /** Send button or Enter — plain chat message. */
    private void onSend() {
        String text = inputField != null ? inputField.getText().trim() : "";
        if (text.isEmpty()) return;
        addMessage("You: " + text);
        ensureConnected(); // reconnect if needed
        if (persistentClient != null && persistentClient.isOpen()) {
            persistentClient.send(text);
        } else {
            // Connection is still opening (async) — retry after 1 second
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

    /** Build button — prefixes [BUILD] so the AI knows to return LOAD_SCHEMATIC. */
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

    /** Add a line to the persistent chat history. */
    public static void addMessage(String msg) {
        persistentHistory.add(msg);
        while (persistentHistory.size() > MAX_HISTORY) {
            persistentHistory.remove(0);
        }
    }

    // ── Input ────────────────────────────────────────────────────────────────────

    @Override
    public boolean keyPressed(KeyInput input) {
        int keyCode = input.key();
        if (keyCode == GLFW.GLFW_KEY_ENTER || keyCode == GLFW.GLFW_KEY_KP_ENTER) {
            onSend();
            return true;
        }
        return super.keyPressed(input);
    }

    @Override
    public boolean shouldCloseOnEsc() {
        return true;
    }

    // ── Rendering ────────────────────────────────────────────────────────────────

    /** Prevent Screen from painting a dirt/blur background over the game world. */
    @Override
    public void renderBackground(DrawContext context, int mouseX, int mouseY, float delta) {
        // intentionally empty — overlay, game world shows through
    }

    @Override
    public void render(DrawContext context, int mouseX, int mouseY, float delta) {
        int pl = panelLeft();
        int pt = panelTop();
        int pr = pl + PANEL_WIDTH;  // right edge
        int pb = pt + PANEL_HEIGHT; // bottom edge

        // ── Panel background ────────────────────────────────────────────────────
        context.fill(pl, pt, pr, pb, COLOR_BG);

        // ── Bottom layout: input + buttons are already widgets; compute their Y ─
        int btnY   = pb - PAD - BTN_HEIGHT;
        int inputY = btnY - PAD - INPUT_HEIGHT;

        // ── Divider above input area ─────────────────────────────────────────────
        context.fill(pl + PAD, inputY - 4, pr - PAD, inputY - 3, COLOR_DIVIDER);

        // ── Chat history (fills the top portion, newest at bottom) ───────────────
        int textAreaTop    = pt + PAD;
        int textAreaBottom = inputY - 8;
        int maxTextWidth   = PANEL_WIDTH - PAD * 2;

        // Build the full list of wrapped display lines from history
        List<String[]> wrappedMessages = new ArrayList<>(); // [prefix, line]
        for (String msg : persistentHistory) {
            String prefix = msg.startsWith("AI: ") ? "AI" :
                            msg.startsWith("You: ") ? "You" : "Sys";
            List<String> lines = wrapText(msg, maxTextWidth);
            for (int i = 0; i < lines.size(); i++) {
                wrappedMessages.add(new String[]{ i == 0 ? prefix : "", lines.get(i) });
            }
        }

        // How many lines fit in the text area?
        int maxLines = (textAreaBottom - textAreaTop) / LINE_HEIGHT;

        // Show only the last maxLines (so newest messages stay visible at bottom)
        int startIdx = Math.max(0, wrappedMessages.size() - maxLines);
        int y = textAreaTop;
        for (int i = startIdx; i < wrappedMessages.size(); i++) {
            String[] entry = wrappedMessages.get(i);
            int color = "AI".equals(entry[0]) ? COLOR_AI :
                        "You".equals(entry[0]) ? COLOR_YOU : COLOR_SYS;
            context.drawText(this.textRenderer, entry[1], pl + PAD, y, color, true);
            y += LINE_HEIGHT;
        }

        // ── Buttons + input field (drawn by super + widget render) ────────────────
        super.render(context, mouseX, mouseY, delta);
        inputField.render(context, mouseX, mouseY, delta);

        // ── Connection dot (top-right corner of panel) ────────────────────────────
        boolean connected = persistentClient != null && persistentClient.isOpen();
        int dotColor = connected ? 0xFF55FF55 : 0xFFFF5555;
        context.drawText(this.textRenderer, "●", pr - 12, pt + 4, dotColor, true);
    }

    /**
     * Word-wrap {@code text} so no line exceeds {@code maxWidth} pixels.
     * Splits on spaces; never produces an empty result.
     */
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
        if (lines.isEmpty()) lines.add(""); // safety
        return lines;
    }

    @Override
    public boolean shouldPause() {
        return false;
    }
}
