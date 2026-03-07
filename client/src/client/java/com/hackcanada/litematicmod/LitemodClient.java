package com.hackcanada.litematicmod;

import net.fabricmc.api.ClientModInitializer;

public class LitemodClient implements ClientModInitializer {
	@Override
	public void onInitializeClient() {
		// This entrypoint is suitable for setting up client-specific logic, such as
		// rendering.
		LitemodCommand.register();
	}
}