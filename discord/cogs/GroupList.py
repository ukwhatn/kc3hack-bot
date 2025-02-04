import csv
import io
import logging
from datetime import datetime

import discord
from discord.commands import slash_command
from sqlalchemy import select

from db.package.models import Group
from db.package.session import get_db


class GroupListInput(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.add_item(discord.ui.InputText(label="グループリスト", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        # レスポンスを遅延
        await interaction.response.defer()

        # データ取得
        # header: id, name, short_name, is_disabled
        raw_data: list[dict] = list(csv.DictReader(self.children[0].value.split("\n")))
        # idをintに変換
        data: list[dict] = []
        for row in raw_data:
            row["id"] = int(row["id"]) if row["id"] != "" else None
            row["is_disabled"] = True if row["is_disabled"] == "1" else False
            data.append(row)

        # idのないものは新規作成
        new_groups = filter(lambda x: x["id"] is None, data)
        # idのあるものは更新
        update_groups = filter(lambda x: x["id"] is not None, data)

        with get_db() as db:
            # 新規グループを更新
            try:
                for group in new_groups:
                    db.add(Group(**group))

                for group in update_groups:
                    _g = db.execute(select(Group).where(Group.id == group["id"])).scalar()
                    if _g:
                        _g.name = group["name"]
                        _g.short_name = group["short_name"]
                        _g.is_disabled = group["is_disabled"]
                        db.add(_g)

                db.commit()
            except Exception as e:
                await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)
                raise e

        await interaction.followup.send("保存しました", ephemeral=True)


class GroupList(discord.Cog):
    def __init__(self):
        self.bot = None
        self.logger = logging.getLogger(__name__)

    @slash_command(name="list_groups", description="グループリストを表示します")
    async def list_groups(self, ctx: discord.commands.context.ApplicationContext):
        # 遅延
        await ctx.interaction.response.defer(ephemeral=True)

        # server adminのみ実行を許可
        if ctx.author.guild_permissions.administrator is False:
            await ctx.interaction.followup.send("このコマンドはサーバー管理者のみ実行可能です", ephemeral=True)
            return

        with get_db() as db:
            groups = db.execute(select(Group)).scalars().all()

        # csv形式に変換
        # header: id, name, short_name, is_disabled
        csv_header = "id,name,short_name,is_disabled"
        csv_body = "\n".join(
            [f"{group.id},{group.name},{group.short_name},{1 if group.is_disabled else 0}" for group in groups]
        )

        csv_data = f"{csv_header}\n{csv_body}"

        # csv_dataを送信
        await ctx.interaction.followup.send(
            "グループリスト",
            file=discord.File(
                filename=f"group_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                fp=io.BytesIO(csv_data.encode("utf-8")),
            )
        )

    @slash_command(name="input_groups", description="グループリストを入力します")
    async def input_groups(self, ctx: discord.commands.context.ApplicationContext):
        # server adminのみ実行を許可
        if ctx.author.guild_permissions.administrator is False:
            await ctx.interaction.followup.send("このコマンドはサーバー管理者のみ実行可能です", ephemeral=True)
            return

        await ctx.send_modal(GroupListInput(title="グループリスト入力"))


def setup(bot):
    bot.add_cog(GroupList())
