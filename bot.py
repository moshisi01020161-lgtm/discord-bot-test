import discord
from discord.ext import commands
from discord.ext import tasks
import json
import os
import requests
from dotenv import load_dotenv
from keep_alive import keep_alive

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# { channel_id: { "message_id": int, "content": str } }
PINNED_DATA_FILE = "pinned_data.json"


def load_pinned_data() -> dict:
    if os.path.exists(PINNED_DATA_FILE):
        with open(PINNED_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_pinned_data(data: dict):
    with open(PINNED_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


pinned_data = load_pinned_data()


async def repost_pinned_message(channel: discord.TextChannel):
    """チャンネルの固定メッセージを削除して再送信する"""
    channel_id_str = str(channel.id)
    if channel_id_str not in pinned_data:
        return

    info = pinned_data[channel_id_str]
    old_message_id = info.get("message_id")
    content = info.get("content", "")

    # 古いメッセージを削除
    if old_message_id:
        try:
            old_msg = await channel.fetch_message(old_message_id)
            await old_msg.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

    # 新しいメッセージを送信
    embed = discord.Embed(
        description=content,
        color=discord.Color.from_rgb(88, 101, 242)  # Discordブランドカラー
    )
    embed.set_footer(text="📌 固定メッセージ")

    new_msg = await channel.send(embed=embed)
    pinned_data[channel_id_str]["message_id"] = new_msg.id
    save_pinned_data(pinned_data)


# ---- セルフping設定 ----
# RENDERのURLを環境変数 RENDER_EXTERNAL_URL に設定してください
# 例: https://your-app-name.onrender.com
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")


@tasks.loop(minutes=14)
async def self_ping():
    """Renderのスリープを防ぐため、14分ごとに自分自身にHTTPリクエストを送る"""
    if not RENDER_URL:
        return
    try:
        res = requests.get(f"{RENDER_URL}/health", timeout=10)
        print(f"💓 Self-ping: {res.status_code}")
    except Exception as e:
        print(f"⚠️ Self-ping 失敗: {e}")


@bot.event
async def on_ready():
    print(f"✅ Botが起動しました: {bot.user} (ID: {bot.user.id})")
    print(f"📌 固定チャンネル数: {len(pinned_data)}")
    if RENDER_URL:
        self_ping.start()
        print(f"💓 Self-ping タスク開始 (対象: {RENDER_URL})")
    else:
        print("ℹ️ RENDER_EXTERNAL_URL が未設定のため Self-ping は無効です")


@bot.event
async def on_message(message: discord.Message):
    # Bot自身のメッセージは無視
    if message.author.bot:
        return

    channel_id_str = str(message.channel.id)

    # 固定メッセージが設定されているチャンネルなら再投稿
    if channel_id_str in pinned_data:
        await repost_pinned_message(message.channel)

    await bot.process_commands(message)


@bot.command(name="setpin")
@commands.has_permissions(manage_messages=True)
async def set_pin(ctx: commands.Context, *, text: str):
    """
    指定したテキストをこのチャンネルの固定メッセージとして設定します。
    使い方: !setpin <メッセージ内容>
    """
    channel_id_str = str(ctx.channel.id)

    # 既存の固定メッセージがあれば削除
    if channel_id_str in pinned_data:
        old_message_id = pinned_data[channel_id_str].get("message_id")
        if old_message_id:
            try:
                old_msg = await ctx.channel.fetch_message(old_message_id)
                await old_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

    # コマンドメッセージを削除（チャットを綺麗に保つ）
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    # データを保存して固定メッセージを投稿
    pinned_data[channel_id_str] = {"message_id": None, "content": text}
    save_pinned_data(pinned_data)

    await repost_pinned_message(ctx.channel)
    print(f"📌 #{ctx.channel.name} に固定メッセージを設定: {text[:50]}...")


@bot.command(name="removepin")
@commands.has_permissions(manage_messages=True)
async def remove_pin(ctx: commands.Context):
    """
    このチャンネルの固定メッセージを解除します。
    使い方: !removepin
    """
    channel_id_str = str(ctx.channel.id)

    if channel_id_str not in pinned_data:
        await ctx.send("❌ このチャンネルには固定メッセージが設定されていません。", delete_after=5)
        return

    # 固定メッセージを削除
    old_message_id = pinned_data[channel_id_str].get("message_id")
    if old_message_id:
        try:
            old_msg = await ctx.channel.fetch_message(old_message_id)
            await old_msg.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

    del pinned_data[channel_id_str]
    save_pinned_data(pinned_data)

    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    await ctx.send("✅ 固定メッセージを解除しました。", delete_after=5)
    print(f"🗑️ #{ctx.channel.name} の固定メッセージを解除しました。")


@bot.command(name="pininfo")
async def pin_info(ctx: commands.Context):
    """現在の固定メッセージの内容を確認します。"""
    channel_id_str = str(ctx.channel.id)

    if channel_id_str not in pinned_data:
        await ctx.send("❌ このチャンネルには固定メッセージが設定されていません。", delete_after=5)
        return

    content = pinned_data[channel_id_str].get("content", "")
    embed = discord.Embed(
        title="📌 現在の固定メッセージ",
        description=content,
        color=discord.Color.green()
    )
    await ctx.send(embed=embed, delete_after=10)


@bot.command(name="say")
async def say_command(ctx: commands.Context, *, text: str):
    """
    入力されたメッセージをBotが代わりに送信します。
    使い方: !say <メッセージ内容>
    """
    # 呼び出し元のコマンドメッセージを削除（権限がある場合）
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    # Botとしてメッセージを送信
    await ctx.send(text)


@set_pin.error
@remove_pin.error
async def permission_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ このコマンドを使用するには「メッセージの管理」権限が必要です。", delete_after=5)


if __name__ == "__main__":
    keep_alive()  # Flaskサーバーをバックグラウンドで起動
    bot.run(TOKEN)
