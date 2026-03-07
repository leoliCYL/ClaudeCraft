package com.hackcanada.litematicmod;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;

import java.net.URI;
import java.util.function.Consumer;

public class BackendClient extends WebSocketClient {

    private Consumer<String> onMessageCallback;

    public BackendClient(URI serverUri, Consumer<String> onMessageCallback) {
        super(serverUri);
        this.onMessageCallback = onMessageCallback;
    }

    @Override
    public void onOpen(ServerHandshake handshakedata) {
        Litemod.LOGGER.info("Connected to WebSocket backend");
    }

    @Override
    public void onMessage(String message) {
        Litemod.LOGGER.info("Received from WebSocket: " + message);
        if (onMessageCallback != null) {
            onMessageCallback.accept(message);
        }
    }

    @Override
    public void onClose(int code, String reason, boolean remote) {
        Litemod.LOGGER.info("Disconnected from WebSocket backend. Reason: " + reason);
    }

    @Override
    public void onError(Exception ex) {
        Litemod.LOGGER.error("WebSocket error", ex);
    }
}
