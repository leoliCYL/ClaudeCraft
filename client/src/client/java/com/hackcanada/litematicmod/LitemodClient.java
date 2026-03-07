package com.hackcanada.litematicmod;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.minecraft.client.option.KeyBinding;
import net.minecraft.client.util.InputUtil;
import net.minecraft.util.Identifier;
import org.lwjgl.glfw.GLFW;

public class LitemodClient implements ClientModInitializer {

	private static KeyBinding toggleOverlayKey;

	@Override
	public void onInitializeClient() {
		LitemodCommand.register();
		registerKeybinds();
	}

	private void registerKeybinds() {
		// Default: B key — opens/closes the AI chat overlay
		toggleOverlayKey = KeyBindingHelper.registerKeyBinding(new KeyBinding(
				"key.litemod.toggle_chat",
				InputUtil.Type.KEYSYM,
				GLFW.GLFW_KEY_B,
				KeyBinding.Category.create(Identifier.of("litemod", "category"))
		));

		ClientTickEvents.END_CLIENT_TICK.register(client -> {
			while (toggleOverlayKey.wasPressed()) {
				if (client.currentScreen instanceof ChatOverlayScreen) {
					client.setScreen(null);
				} else {
					client.setScreen(new ChatOverlayScreen());
				}
			}
		});
	}
}