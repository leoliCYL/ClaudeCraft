package com.hackcanada.claudecraft;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.TextFieldWidget;
import net.minecraft.text.Text;
import org.lwjgl.glfw.GLFW;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.ArrayList;
import java.util.List;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

public class ChatOverlayScreen extends Screen {

    private TextFieldWidget inputField;
    private ButtonWidget sendButton;
    private BackendClient webSocketClient;
    private final List<String> chatHistory = new ArrayList<>();

    // A singleton to persist the connection across screen opens
    public static BackendClient persistentClient;
    public static final List<String> persistentHistory = new ArrayList<>();

    // Build progress tracking
    private static int buildTotalLayers = 0;
    private static int buildCurrentLayer = 0;
    private static boolean isBuilding = false;

    public ChatOverlayScreen() {
        super(Text.literal("AI Chat"));
    }

    @Override
    protected void init() {
        super.init();

        int bottomY = this.height - 30;
        this.inputField = new TextFieldWidget(this.textRenderer, this.width - 210, bottomY - 30, 200, 20,
                Text.literal("Ask AI..."));
        this.inputField.setMaxLength(256);
        this.inputField.setDrawsBackground(true);
        this.addSelectableChild(this.inputField);
        this.setInitialFocus(this.inputField);

        this.sendButton = ButtonWidget.builder(Text.literal("Send"), button -> {
            sendChatMessage();
        })
                .dimensions(this.width - 210, bottomY, 200, 20)
                .build();
        this.addDrawableChild(this.sendButton);

        chatHistory.addAll(persistentHistory);

        if (persistentClient == null || persistentClient.isClosed()) {
            try {
                persistentClient = new BackendClient(new URI("ws://127.0.0.1:8080"), this::handleIncomingMessage);
                persistentClient.connect();
            } catch (URISyntaxException e) {
                ClaudeCraft.LOGGER.error("Invalid WebSocket URI", e);
            }
        } else {
            persistentClient.setOnMessageCallback(this::handleIncomingMessage);
        }

        this.webSocketClient = persistentClient;
    }

    private void handleIncomingMessage(String message) {
        // Try to parse as JSON first (BUILD_START, BUILD_LAYER, BUILD_DONE)
        if (message.startsWith("{")) {
            try {
                JsonObject json = JsonParser.parseString(message).getAsJsonObject();
                String type = json.has("type") ? json.get("type").getAsString() : "";

                switch (type) {
                    case "BUILD_START":
                        handleBuildStart(json);
                        return;
                    case "BUILD_LAYER":
                        handleBuildLayer(json);
                        return;
                    case "BUILD_DONE":
                        handleBuildDone();
                        return;
                    default:
                        break;
                }
            } catch (Exception e) {
                ClaudeCraft.LOGGER.warn("Failed to parse JSON message: " + e.getMessage());
                // Fall through to treat as plain text
            }
        }

        // Plain text message from AI
        MinecraftClient.getInstance().execute(() -> {
            addMessage("AI: " + message);
        });
    }

    private void handleBuildStart(JsonObject json) {
        String name = json.has("name") ? json.get("name").getAsString() : "Unknown";
        int totalLayers = json.has("totalLayers") ? json.get("totalLayers").getAsInt() : 0;

        buildTotalLayers = totalLayers;
        buildCurrentLayer = 0;
        isBuilding = true;

        MinecraftClient.getInstance().execute(() -> {
            addMessage("Building: " + name + " (" + totalLayers + " layers)");
        });

        ClaudeCraft.LOGGER.info("BUILD_START: " + name + " with " + totalLayers + " layers");
    }

    private void handleBuildLayer(JsonObject json) {
        int layerIndex = json.has("layerIndex") ? json.get("layerIndex").getAsInt() : 0;
        int yLevel = json.has("yLevel") ? json.get("yLevel").getAsInt() : 0;
        JsonArray blocks = json.has("blocks") ? json.get("blocks").getAsJsonArray() : new JsonArray();

        buildCurrentLayer = layerIndex + 1;

        ClaudeCraft.LOGGER.info("BUILD_LAYER " + buildCurrentLayer + "/" + buildTotalLayers
                + ": Y=" + yLevel + ", " + blocks.size() + " blocks");

        // Place blocks on the server thread
        MinecraftClient mc = MinecraftClient.getInstance();
        if (mc.player != null && mc.getServer() != null) {
            net.minecraft.util.math.BlockPos playerPos = mc.player.getBlockPos();
            net.minecraft.server.world.ServerWorld serverWorld = mc.getServer()
                    .getWorld(mc.world.getRegistryKey());

            mc.getServer().execute(() -> {
                SchematicHelper.placeBlocksFromJson(serverWorld, playerPos, blocks);
            });
        }

        // Update chat progress periodically (every 3 layers or last layer)
        if (buildCurrentLayer == 1 || buildCurrentLayer % 3 == 0
                || buildCurrentLayer == buildTotalLayers) {
            MinecraftClient.getInstance().execute(() -> {
                addMessage("Building layer " + buildCurrentLayer + "/" + buildTotalLayers + "...");
            });
        }
    }

    private void handleBuildDone() {
        isBuilding = false;
        MinecraftClient.getInstance().execute(() -> {
            addMessage("Build complete!");
        });
        ClaudeCraft.LOGGER.info("BUILD_DONE");
    }

    private void addMessage(String msg) {
        chatHistory.add(msg);
        persistentHistory.add(msg);
        if (chatHistory.size() > 15) {
            chatHistory.remove(0);
        }
        if (persistentHistory.size() > 15) {
            persistentHistory.remove(0);
        }
    }

    private void sendChatMessage() {
        String text = this.inputField.getText().trim();
        if (!text.isEmpty()) {
            addMessage("You: " + text);
            if (webSocketClient != null && webSocketClient.isOpen()) {
                webSocketClient.send(text);
            } else {
                addMessage("System: Not connected to backend!");
            }
            this.inputField.setText("");
        }
    }

    @Override
    public boolean keyPressed(net.minecraft.client.input.KeyInput input) {
        int keyCode = input.key();
        if (keyCode == GLFW.GLFW_KEY_ENTER || keyCode == GLFW.GLFW_KEY_KP_ENTER) {
            sendChatMessage();
            return true;
        }
        return super.keyPressed(input);
    }

    @Override
    public void tick() {
        super.tick();
        if (this.sendButton != null && this.inputField != null) {
            this.sendButton.active = !this.inputField.getText().trim().isEmpty();
        }
    }

    @Override
    public void render(DrawContext context, int mouseX, int mouseY, float delta) {
        // Render the chat box background
        context.fill(this.width - 220, 0, this.width, this.height, 0x88000000);

        super.render(context, mouseX, mouseY, delta);
        this.inputField.render(context, mouseX, mouseY, delta);

        // Render chat history sequentially from bottom upwards
        int y = this.height - 75;
        for (int i = chatHistory.size() - 1; i >= 0; i--) {
            String msg = chatHistory.get(i);
            context.drawText(this.textRenderer, msg, this.width - 210, y, 0xFFFFFF, true);
            y -= 12;
        }

        // Render build progress bar if building
        if (isBuilding && buildTotalLayers > 0) {
            int barX = this.width - 210;
            int barY = this.height - 65;
            int barWidth = 200;
            int barHeight = 4;
            float progress = (float) buildCurrentLayer / buildTotalLayers;

            // Background
            context.fill(barX, barY, barX + barWidth, barY + barHeight, 0xFF333333);
            // Progress fill
            context.fill(barX, barY, barX + (int) (barWidth * progress), barY + barHeight, 0xFF55FF55);
        }
    }

    @Override
    public boolean shouldPause() {
        return false;
    }
}
