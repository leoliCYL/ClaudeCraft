package com.hackcanada.claudecraft;

import net.fabricmc.api.ClientModInitializer;

import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.MinecraftClient;

public class ClaudeCraftClient implements ClientModInitializer {
	@Override
	public void onInitializeClient() {
		// This entrypoint is suitable for setting up client-specific logic, such as
		// rendering.
		ClaudeCraftCommand.register();
		ClaudeCraft.LOGGER.info("Claude Craft client initialized! Try /cc gui");

		HudRenderCallback.EVENT.register((context, tickDeltaManager) -> {
			if (ChatOverlayScreen.persistentHistory != null) {
				int y = 5;
				for (int i = Math.max(0,
						ChatOverlayScreen.persistentHistory.size() - 8); i < ChatOverlayScreen.persistentHistory
								.size(); i++) {
					String msg = ChatOverlayScreen.persistentHistory.get(i);
					context.drawText(MinecraftClient.getInstance().textRenderer, msg, 5, y, 0xFFFFFF, true);
					y += 10;
				}
			}
		});
	}
}