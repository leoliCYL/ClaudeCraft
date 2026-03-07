package com.hackcanada.litematicmod;

import com.mojang.brigadier.arguments.StringArgumentType;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource;
import net.minecraft.command.argument.BlockPosArgumentType;
import net.minecraft.text.Text;

import static net.fabricmc.fabric.api.client.command.v2.ClientCommandManager.argument;
import static net.fabricmc.fabric.api.client.command.v2.ClientCommandManager.literal;

import net.minecraft.client.MinecraftClient;

public class LitemodCommand {
        public static void register() {
                ClientCommandRegistrationCallback.EVENT.register((dispatcher, registryAccess) -> {
                        dispatcher.register(literal("litemod")
                                        .then(literal("gui")
                                                        .executes(context -> {
                                                                FabricClientCommandSource source = context.getSource();
                                                                source.sendFeedback(Text.literal("Opening GUI..."));
                                                                MinecraftClient.getInstance().send(() -> {
                                                                        MinecraftClient.getInstance()
                                                                                        .setScreen(new ChatOverlayScreen());
                                                                });
                                                                return 1;
                                                        }))
                                        .then(literal("save")
                                                        .then(argument("pos1", BlockPosArgumentType.blockPos())
                                                                        .then(argument("pos2",
                                                                                        BlockPosArgumentType.blockPos())
                                                                                        .then(argument("filename",
                                                                                                        StringArgumentType
                                                                                                                        .word())
                                                                                                        .executes(context -> {
                                                                                                                FabricClientCommandSource source = context
                                                                                                                                .getSource();
                                                                                                                String filename = StringArgumentType
                                                                                                                                .getString(context,
                                                                                                                                                "filename");
                                                                                                                net.minecraft.command.argument.DefaultPosArgument arg1 = context
                                                                                                                                .getArgument("pos1",
                                                                                                                                                net.minecraft.command.argument.DefaultPosArgument.class);
                                                                                                                net.minecraft.util.math.BlockPos pos1 = net.minecraft.util.math.BlockPos
                                                                                                                                .ofFloored(
                                                                                                                                                arg1.x().toAbsoluteCoordinate(
                                                                                                                                                                source.getPlayer()
                                                                                                                                                                                .getX()),
                                                                                                                                                arg1.y().toAbsoluteCoordinate(
                                                                                                                                                                source.getPlayer()
                                                                                                                                                                                .getY()),
                                                                                                                                                arg1.z().toAbsoluteCoordinate(
                                                                                                                                                                source.getPlayer()
                                                                                                                                                                                .getZ()));
                                                                                                                net.minecraft.command.argument.DefaultPosArgument arg2 = context
                                                                                                                                .getArgument("pos2",
                                                                                                                                                net.minecraft.command.argument.DefaultPosArgument.class);
                                                                                                                net.minecraft.util.math.BlockPos pos2 = net.minecraft.util.math.BlockPos
                                                                                                                                .ofFloored(
                                                                                                                                                arg2.x().toAbsoluteCoordinate(
                                                                                                                                                                source.getPlayer()
                                                                                                                                                                                .getX()),
                                                                                                                                                arg2.y().toAbsoluteCoordinate(
                                                                                                                                                                source.getPlayer()
                                                                                                                                                                                .getY()),
                                                                                                                                                arg2.z().toAbsoluteCoordinate(
                                                                                                                                                                source.getPlayer()
                                                                                                                                                                                .getZ()));

                                                                                                                if (MinecraftClient
                                                                                                                                .getInstance().world != null) {
                                                                                                                        LitematicaHelper.saveLitematica(
                                                                                                                                        MinecraftClient.getInstance().world,
                                                                                                                                        pos1,
                                                                                                                                        pos2,
                                                                                                                                        filename);
                                                                                                                        source.sendFeedback(
                                                                                                                                        Text.literal("Saved Litematica file "
                                                                                                                                                        + filename
                                                                                                                                                        + ".litematic"));
                                                                                                                } else {
                                                                                                                        source.sendError(
                                                                                                                                        Text.literal("World is not loaded."));
                                                                                                                }
                                                                                                                return 1;
                                                                                                        })))))
                                        .then(literal("load")
                                                        .then(argument("filename", StringArgumentType.word())
                                                                        .then(argument("pos",
                                                                                        BlockPosArgumentType.blockPos())
                                                                                        .executes(context -> {
                                                                                                FabricClientCommandSource source = context
                                                                                                                .getSource();
                                                                                                String filename = StringArgumentType
                                                                                                                .getString(context,
                                                                                                                                "filename");
                                                                                                net.minecraft.command.argument.DefaultPosArgument argPos = context
                                                                                                                .getArgument("pos",
                                                                                                                                net.minecraft.command.argument.DefaultPosArgument.class);
                                                                                                net.minecraft.util.math.BlockPos pos = net.minecraft.util.math.BlockPos
                                                                                                                .ofFloored(
                                                                                                                                argPos.x().toAbsoluteCoordinate(
                                                                                                                                                source.getPlayer()
                                                                                                                                                                .getX()),
                                                                                                                                argPos.y().toAbsoluteCoordinate(
                                                                                                                                                source.getPlayer()
                                                                                                                                                                .getY()),
                                                                                                                                argPos.z().toAbsoluteCoordinate(
                                                                                                                                                source.getPlayer()
                                                                                                                                                                .getZ()));

                                                                                                if (MinecraftClient
                                                                                                                .getInstance().world != null) {
                                                                                                        LitematicaHelper.loadLitematica(
                                                                                                                        MinecraftClient.getInstance().world,
                                                                                                                        pos,
                                                                                                                        filename);
                                                                                                        source.sendFeedback(
                                                                                                                        Text.literal("Loaded Litematica file "
                                                                                                                                        + filename
                                                                                                                                        + ".litematic"));
                                                                                                } else {
                                                                                                        source.sendError(
                                                                                                                        Text.literal("World is not loaded."));
                                                                                                }
                                                                                                return 1;
                                                                                        })))));
                });
        }
}
