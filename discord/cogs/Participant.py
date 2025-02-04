import csv
import io
import logging
from datetime import datetime

import discord
from discord.commands import slash_command
from sqlalchemy import select

from db.package.models import Group, Participant, UserSessionStorage
from db.package.session import get_db


class ParticipantInfoModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.add_item(discord.ui.InputText(label="姓（漢字）", style=discord.InputTextStyle.short))
        self.add_item(discord.ui.InputText(label="名（漢字）", style=discord.InputTextStyle.short))
        self.add_item(discord.ui.InputText(label="GitHubユーザページのURL", style=discord.InputTextStyle.short, placeholder='https://github.com/xxxxx'))

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


class GroupSelectorView(discord.ui.view):
    @staticmethod
    def get_group_names():
        with get_db() as db:
            # activeなグループを取得
            groups = db.execute(select(Group).where(Group.is_disabled is False)).scalars().all()
            return [(group.id, group.name) for group in groups]

    @discord.ui.select(
        placeholder="所属団体を選択してください",
        options=[
            discord.SelectOption(
                label=group_name,
                value=str(group_id)
            ) for group_id, group_name in get_group_names()
        ],
        custom_id="group_selector",
        min_values=1,
        max_values=1
    )
    async def callback(self, s: discord.ui.Select, interaction: discord.Interaction):
        # 遅延
        await interaction.response.defer(ephemeral=True)

        # データ取得
        group_id = int(s.values[0])
        author_id = interaction.user.id

        with get_db() as db:
            # グループ取得
            group = db.execute(select(Group).where(Group.id == group_id)).scalar()
            if not group:
                await interaction.response.send_message("グループが見つかりません。再度お試しください。", ephemeral=True)
                return

            # セッションに保存
            user_session = db.execute(
                select(UserSessionStorage).where(UserSessionStorage.user_id == author_id)
            ).scalar()
            if not user_session:
                user_session = UserSessionStorage(user_id=author_id, data={})
            user_session.data["group_id"] = group_id
            db.add(user_session)
            db.commit()

