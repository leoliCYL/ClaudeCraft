package com.hackcanada.claudecraft;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;

import java.net.URI;
import java.nio.ByteBuffer;
import java.util.function.Consumer;

public class BackendClient extends WebSocketClient {

    private Consumer<String> onMessageCallback;
    private Consumer<ByteBuffer> onBinaryMessageCallback;

    public BackendClient(URI serverUri, Consumer<String> onMessageCallback) {
        super(serverUri);
        this.onMessageCallback = onMessageCallback;
    }

    public void setOnMessageCallback(Consumer<String> onMessageCallback) {
        this.onMessageCallback = onMessageCallback;
    }

    public void setOnBinaryMessageCallback(Consumer<ByteBuffer> onBinaryMessageCallback) {
        this.onBinaryMessageCallback = onBinaryMessageCallback;
    }

    @Override
    public void onOpen(ServerHandshake handshakedata) {
        ClaudeCraft.LOGGER.info("Connected to WebSocket backend");
    }

    @Override
    public void onMessage(String message) {
        ClaudeCraft.LOGGER.info("Received from WebSocket: " + message);
        if (onMessageCallback != null) {
            onMessageCallback.accept(message);
        }
    }

    @Override
    public void onMessage(ByteBuffer bytes) {
        ClaudeCraft.LOGGER.info("Received binary data from WebSocket. Size: " + bytes.capacity());
        if (onBinaryMessageCallback != null) {
            onBinaryMessageCallback.accept(bytes);
        }
    }

    @Override
    public void onClose(int code, String reason, boolean remote) {
        ClaudeCraft.LOGGER.info("Disconnected from WebSocket backend. Reason: " + reason);
    }

    @Override
    public void onError(Exception ex) {
        ClaudeCraft.LOGGER.error("WebSocket error", ex);
    }
}
