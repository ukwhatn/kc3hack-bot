import io
from datetime import datetime

import discord
from discord import slash_command
from discord.ext import commands
from sqlalchemy import select

from db.package.models import VoiceChatLog, TextChatLog
from db.package.session import get_db


class Logger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ボイスチャットログ
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not isinstance(member, discord.Member):
            return

        # メンバーのロールから"チーム"で始まるものを取得し、チームIDとする
        team_id = None
        for role in member.roles:
            if role.name.startswith("チーム"):
                team_id = role.name.removeprefix("チーム")
                break

        if team_id is None:
            return

        if before.channel is None and after.channel is not None:
            with get_db() as db:
                db.add(
                    VoiceChatLog(
                        channel_id=after.channel.id,
                        team_id=team_id,
                        start_time=datetime.now(),
                        end_time=None,
                    )
                )
                db.commit()
        elif before.channel is not None and after.channel is None:
            with get_db() as db:
                _t = db.execute(
                    select(VoiceChatLog)
                    .where(VoiceChatLog.channel_id == before.channel.id)
                    .order_by(VoiceChatLog.start_time.desc())
                    .limit(1)
                ).scalar()

                if _t:
                    _t.end_time = datetime.now()
                    db.add(_t)
                    db.commit()

    # テキストチャットログ
    @commands.Cog.listener()
    async def on_message(self, message):
        if not isinstance(message.author, discord.Member):
            return

        # メンバーのロールから"チーム"で始まるものを取得し、チームIDとする
        team_id = None
        for role in message.author.roles:
            if role.name.startswith("チーム"):
                team_id = role.name.removeprefix("チーム")
                break

        if team_id is None:
            return

        with get_db() as db:
            db.add(
                TextChatLog(
                    channel_id=message.channel.id,
                    team_id=team_id,
                    message_id=message.id,
                )
            )
            db.commit()

    @slash_command(name="list_voice_chat_logs", description="ボイスチャットログを表示します")
    @commands.has_permissions(administrator=True)
    async def list_voice_chat_logs(self, ctx):
        await ctx.response.defer(ephemeral=True)
        with get_db() as db:
            logs = db.execute(select(VoiceChatLog)).scalars().all()

        # チームごとに合計時間を計算
        team_logs = {}
        for log in logs:
            if log.end_time is None:
                continue
            if log.team_id not in team_logs:
                team_logs[log.team_id] = 0
            team_logs[log.team_id] += (log.end_time - log.start_time).seconds

        # 多い順にソート
        sorted_team_logs = sorted(team_logs.items(), key=lambda x: x[1], reverse=True)

        # メッセージ作成
        message = "```"
        for team_id, total_time in sorted_team_logs:
            message += f"チーム{team_id}: {total_time}秒\n"
        message += "```"

        await ctx.followup.send(message, ephemeral=True)

    @slash_command(name='output_text_csv', description='テキストチャットログをCSV形式で出力します')
    @commands.has_permissions(administrator=True)
    async def output_text_csv(self, ctx):
        await ctx.response.defer(ephemeral=True)

        with get_db() as db:
            logs = db.execute(select(TextChatLog)).scalars().all()

        csv_header = "team_id,channel_id,message_id,created_at"
        csv_body = "\n".join(
            [
                f"{log.team_id},{log.channel_id},{log.message_id},{log.created_at}"
                for log in logs
            ]
        )

        # メッセージ作成
        await ctx.followup.send(
            "テキストチャットログ",
            file=discord.File(
                fp=io.BytesIO(f"{csv_header}\n{csv_body}".encode('utf-8')),
                filename="text_chat_logs.csv"
            ),
            ephemeral=True
        )

    @slash_command(name="list_text_chat_logs", description="テキストチャットログを表示します")
    @commands.has_permissions(administrator=True)
    async def list_text_chat_logs(self, ctx):
        await ctx.response.defer(ephemeral=True)

        with get_db() as db:
            logs = db.execute(select(TextChatLog)).scalars().all()

        # チームごとにメッセージ数を計算
        team_logs = {}
        for log in logs:
            if log.team_id not in team_logs:
                team_logs[log.team_id] = 0
            team_logs[log.team_id] += 1

        # 多い順にソート
        sorted_team_logs = sorted(team_logs.items(), key=lambda x: x[1], reverse=True)

        # メッセージ作成
        message = "```"
        for team_id, total_messages in sorted_team_logs:
            message += f"チーム{team_id}: {total_messages}メッセージ\n"
        message += "```"

        await ctx.followup.send(message, ephemeral=True)

    @slash_command(name="output_voice_csv", description="ボイスチャットログをCSV形式で出力します")
    @commands.has_permissions(administrator=True)
    async def output_voice_csv(self, ctx):
        await ctx.response.defer(ephemeral=True)

        with get_db() as db:
            logs = db.execute(select(VoiceChatLog)).scalars().all()

        csv_header = "team_id,channel_id,start_time,end_time"
        csv_body = "\n".join(
            [
                f"{log.team_id},{log.channel_id},{log.start_time},{log.end_time}"
                for log in logs
            ]
        )

        # メッセージ作成
        await ctx.followup.send(
            "ボイスチャットログ",
            file=discord.File(
                fp=io.BytesIO(f"{csv_header}\n{csv_body}".encode('utf-8')),
                filename="voice_chat_logs.csv"
            ),
            ephemeral=True
        )


def setup(bot):
    return bot.add_cog(Logger(bot))
