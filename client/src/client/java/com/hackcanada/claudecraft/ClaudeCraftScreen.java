package com.hackcanada.claudecraft;

import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.text.Text;

public class ClaudeCraftScreen extends Screen {
    protected ClaudeCraftScreen() {
        super(Text.literal("ClaudeCraft Actions"));
        ClaudeCraft.LOGGER.info("Opening ClaudeCraft Configuration Screen");
    }

    @Override
    protected void init() {
        super.init();

        this.addDrawableChild(ButtonWidget.builder(Text.literal("Save Litematica"), button -> {
            // TODO: Open Save UI or execute save
            if (this.client != null) {
                this.client.player.sendMessage(Text.literal("Save clicked! Use /litemod save to perform the action."),
                        false);
                this.client.setScreen(null);
            }
        }).dimensions(this.width / 2 - 100, this.height / 2 - 24, 200, 20).build());

        this.addDrawableChild(ButtonWidget.builder(Text.literal("Load Litematica"), button -> {
            // TODO: Open Load UI or execute load
            if (this.client != null) {
                this.client.player.sendMessage(Text.literal("Load clicked! Use /litemod load to perform the action."),
                        false);
                this.client.setScreen(null);
            }
        }).dimensions(this.width / 2 - 100, this.height / 2 + 4, 200, 20).build());
    }
}
