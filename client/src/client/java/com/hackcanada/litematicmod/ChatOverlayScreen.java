package com.hackcanada.litematicmod;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.widget.TextFieldWidget;
import net.minecraft.text.Text;
import org.lwjgl.glfw.GLFW;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.ArrayList;
import java.util.List;

public class ChatOverlayScreen extends Screen {

    private TextFieldWidget inputField;
    private BackendClient webSocketClient;
    private final List<String> chatHistory = new ArrayList<>();

    // A singleton to persist the connection across screen opens
    private static BackendClient persistentClient;
    private static final List<String> persistentHistory = new ArrayList<>();

    public ChatOverlayScreen() {
        super(Text.literal("AI Chat"));
    }

    @Override
    protected void init() {
        super.init();

        this.inputField = new TextFieldWidget(this.textRenderer, this.width - 210, 10, 200, 20,
                Text.literal("Ask AI..."));
        this.inputField.setMaxLength(256);
        this.inputField.setDrawsBackground(true);
        this.addSelectableChild(this.inputField);
        this.setInitialFocus(this.inputField);

        chatHistory.addAll(persistentHistory);

        if (persistentClient == null || !persistentClient.isOpen()) {
            try {
                // Connect to localhost backend (You can configure this later)
                persistentClient = new BackendClient(new URI("ws://localhost:8080"), this::handleIncomingMessage);
                persistentClient.connect();
            } catch (URISyntaxException e) {
                Litemod.LOGGER.error("Invalid WebSocket URI", e);
            }
        } else {
            // Update the callback to point to this instance
            persistentClient = new BackendClient(persistentClient.getURI(), this::handleIncomingMessage);
            // We just swapped clients so we need to reconnect, let's keep it simple and
            // just create a new connection for now if needed, or better yet, reuse the old
            // one and just update a static callback
        }

        this.webSocketClient = persistentClient;
    }

    private void handleIncomingMessage(String message) {
        MinecraftClient.getInstance().execute(() -> {
            addMessage("AI: " + message);

            // Very simple parser to test schematic loading
            if (message.startsWith("LOAD_SCHEMATIC ")) {
                String filename = message.substring("LOAD_SCHEMATIC ".length()).trim();
                if (client != null && client.player != null) {
                    client.player.sendMessage(Text.literal("AI requested to load schematic: " + filename), false);
                    LitematicaHelper.loadLitematica(client.world, client.player.getBlockPos(), filename);
                }
            }
        });
    }

    private void addMessage(String msg) {
        chatHistory.add(msg);
        persistentHistory.add(msg);
        // keep history small
        if (chatHistory.size() > 10) {
            chatHistory.remove(0);
        }
        if (persistentHistory.size() > 10) {
            persistentHistory.remove(0);
        }
    }

    @Override
    public boolean keyPressed(net.minecraft.client.input.KeyInput input) {
        int keyCode = input.key();
        if (keyCode == GLFW.GLFW_KEY_ENTER || keyCode == GLFW.GLFW_KEY_KP_ENTER) {
            String text = this.inputField.getText().trim();
            if (!text.isEmpty()) {
                addMessage("You: " + text);
                if (webSocketClient != null && webSocketClient.isOpen()) {
                    webSocketClient.send(text);
                } else {
                    addMessage("System: Not connected to backend!");
                }
                this.inputField.setText("");
                return true;
            }
        }
        return super.keyPressed(input);
    }

    @Override
    public void render(DrawContext context, int mouseX, int mouseY, float delta) {
        super.render(context, mouseX, mouseY, delta);

        // Render the chat box background
        context.fill(this.width - 220, 0, this.width, this.height, 0x88000000); // Semi-transparent black on the right

        this.inputField.render(context, mouseX, mouseY, delta);

        // Render chat history
        int y = 40;
        for (String msg : chatHistory) {
            context.drawText(this.textRenderer, msg, this.width - 210, y, 0xFFFFFF, true);
            y += 12;
        }
    }

    @Override
    public boolean shouldPause() {
        return false; // Don't pause the game when typing to AI
    }
}
