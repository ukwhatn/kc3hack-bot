import logging

import discord
from discord import slash_command
from discord.ext import commands
from sqlalchemy import select

from db.package.models import Group, Participant, UserSessionStorage
from db.package.session import get_db


class ParticipantInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(ParticipantInputStartButton())
        self.bot.add_view(GroupSelectorView())
        self.bot.add_view(ParticipantInfoModalOpenButton())
        self.bot.add_view(ParticipantInfoConfirmButton())

    @slash_command(
        name="send_participant_info_button", description="参加者情報入力ボタンを送信"
    )
    async def send_participant_info_button(self, ctx: discord.ApplicationContext):
        # Adminに限定
        if not ctx.author.guild_permissions.administrator:
            await ctx.respond(
                "このコマンドはサーバー管理者のみ実行可能です", ephemeral=True
            )
            return

        await ctx.respond(
            "\n".join(
                [
                    "# KC3Hack 参加学生の皆さんへ",
                    "**以下のボタンから、参加者情報の入力をお願いいたします！**",
                    "",
                    "## 注意事項",
                    "> - **参加者情報の入力は必須です。**実施いただけない場合、チームロールの付与を行うことができません。",
                    "> - GitHubアカウントをご入力いただきます。KC3Hackで利用したいアカウントのプロフィールページURL（`https://github.com/xxxx`）をご準備ください。",
                    ">   - ご入力いただいたアカウントに対して、運営が作成したリポジトリへの招待を送信させていただきます。",
                    "> - 情報を更新したい場合、再度同様にボタンを押下して情報を入力してください。"
                    "",
                    "## ご入力いただく情報",
                    "> - 氏名（漢字）",
                    "> - GitHubアカウントのURL",
                    "> - 所属団体",
                    "",
                    "### ---------------",
                ]
            ),
            view=ParticipantInputStartButton(),
        )


class ParticipantInputStartButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="参加者情報を入力・更新する",
        style=discord.ButtonStyle.primary,
        custom_id="start_participant_info_input",
    )
    async def callback(self, _b: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            "### 以下から所属団体を選択してください：",
            ephemeral=True,
            view=GroupSelectorView(),
        )


class GroupSelectorView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @staticmethod
    def get_group_names():
        try:
            with get_db() as db:
                # activeなグループを取得
                groups = (
                    db.execute(
                        select(Group)
                        .where(Group.is_disabled.is_(False))
                        .order_by(Group.id)
                    )
                    .scalars()
                    .all()
                )
                return [(group.id, group.name) for group in groups]
        except Exception:
            return []

    @discord.ui.select(
        placeholder="所属団体を選択してください",
        options=[
            discord.SelectOption(label=group_name, value=str(group_id))
            for group_id, group_name in get_group_names()
        ],
        custom_id="group_selector",
        min_values=1,
        max_values=1,
    )
    async def callback(self, s: discord.ui.Select, interaction: discord.Interaction):
        # 遅延
        await interaction.response.defer(ephemeral=True)

        # データ取得
        group_id = int(s.values[0])
        author_id = interaction.user.id

        try:
            with get_db() as db:
                # グループ取得
                group = db.execute(select(Group).where(Group.id == group_id)).scalar()
                if not group:
                    await interaction.followup.send(
                        "グループが見つかりません。再度選択してください。",
                        ephemeral=True,
                    )
                    return

                # セッションに保存
                user_session = db.execute(
                    select(UserSessionStorage).where(
                        UserSessionStorage.user_id == author_id
                    )
                ).scalar()
                if not user_session:
                    user_session = UserSessionStorage(user_id=author_id, data={})
                user_session.data["group_id"] = group_id
                db.add(user_session)
                db.commit()

                await interaction.followup.send(
                    f"### 続いて、他の情報入力を行ってください：",
                    ephemeral=True,
                    view=ParticipantInfoModalOpenButton(),
                )
        except Exception as e:
            await interaction.followup.send(
                f"エラーが発生しました。再度お試しください。", ephemeral=True
            )
            raise e


class ParticipantInfoModalOpenButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="参加者情報入力フォームを開く",
        style=discord.ButtonStyle.secondary,
        custom_id="open_participant_info_modal",
    )
    async def callback(self, _b: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(
            ParticipantInfoModal(title="参加者情報入力")
        )


class ParticipantInfoModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.add_item(
            discord.ui.InputText(
                label="姓（漢字）",
                style=discord.InputTextStyle.short,
                placeholder="関西",
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="名（漢字）",
                style=discord.InputTextStyle.short,
                placeholder="太郎",
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="GitHubユーザページのURL",
                style=discord.InputTextStyle.short,
                placeholder="https://github.com/xxxxx",
            )
        )

    async def callback(self, interaction: discord.Interaction):
        # レスポンスを遅延
        await interaction.response.defer(ephemeral=True)

        # データ取得
        last_name = self.children[0].value.strip()
        first_name = self.children[1].value.strip()
        github_url = self.children[2].value.strip()

        # GitHub URLのバリデーション
        if not github_url.startswith("https://github.com/") or len(github_url) < 20:
            await interaction.followup.send(
                "GitHubのURLが正しくありません。再度お試しください。", ephemeral=True
            )
            return

        # セッションに保存
        author_id = interaction.user.id
        try:
            with get_db() as db:
                user_session = db.execute(
                    select(UserSessionStorage).where(
                        UserSessionStorage.user_id == author_id
                    )
                ).scalar()
                if not user_session:
                    # セッションがない場合はエラー
                    await interaction.followup.send(
                        "団体名の入力にエラーがあります。再度初めからお試しください。",
                        ephemeral=True,
                    )
                    return

                # セッションに保存
                group_id = user_session.data.get("group_id")

                group_name = db.execute(
                    select(Group.name).where(Group.id == group_id)
                ).scalar()

                if not group_name:
                    await interaction.followup.send(
                        "グループが見つかりません。再度お試しください。", ephemeral=True
                    )
                    return

                data = {
                    "last_name": last_name,
                    "first_name": first_name,
                    "github_url": github_url,
                    "group_id": group_id,
                }
                user_session.data = data
                db.commit()

            await interaction.followup.send(
                "### 以下の情報で登録しますか？\n"
                f"> **名前:** {last_name} {first_name}\n"
                f"> **GitHub:** {github_url}\n"
                f"> **所属団体:** {group_name}",
                ephemeral=True,
                view=ParticipantInfoConfirmButton(),
            )

        except Exception as e:
            await interaction.followup.send(
                "エラーが発生しました。再度お試しください。", ephemeral=True
            )
            raise e


class ParticipantInfoConfirmButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="保存", style=discord.ButtonStyle.success, custom_id="confirm"
    )
    async def callback(self, _b: discord.ui.Button, interaction: discord.Interaction):
        # レスポンスを遅延
        await interaction.response.defer(ephemeral=True)

        # データ取得
        author_id = interaction.user.id
        try:
            with get_db() as db:
                user_session = db.execute(
                    select(UserSessionStorage).where(
                        UserSessionStorage.user_id == author_id
                    )
                ).scalar()
                if not user_session:
                    await interaction.followup.send(
                        "セッションが見つかりません。再度お試しください。"
                    )
                    return

                group_id = user_session.data.get("group_id")
                if not group_id:
                    await interaction.followup.send(
                        "グループが見つかりません。再度お試しください。"
                    )
                    return

                # データ取得
                last_name = user_session.data.get("last_name")
                first_name = user_session.data.get("first_name")
                github_url = user_session.data.get("github_url")

                logging.info(f"last_name: {last_name}")
                logging.info(f"first_name: {first_name}")
                logging.info(f"github_url: {github_url}")
                logging.info(f"group_id: {group_id}")

                # パラメータチェック
                if not last_name or not first_name or not github_url:
                    await interaction.followup.send(
                        "未入力の項目があります。再度お試しください。", ephemeral=True
                    )
                    return

                # データ登録
                # 存在チェック
                participant = db.execute(
                    select(Participant).where(Participant.discord_user_id == author_id)
                ).scalar()

                if participant:
                    # 既存の場合は更新
                    participant.last_name = last_name
                    participant.first_name = first_name
                    participant.github_user_name = github_url
                    participant.group_id = group_id
                    db.add(participant)
                    db.commit()

                    # メッセージ送信
                    group = db.execute(
                        select(Group).where(Group.id == group_id)
                    ).scalar()
                    await interaction.followup.send(
                        f"### 更新しました！",
                        ephemeral=True,
                    )
                else:
                    # 新規登録
                    db.add(
                        Participant(
                            last_name=last_name,
                            first_name=first_name,
                            group_id=group_id,
                            github_user_name=github_url,
                            discord_user_id=author_id,
                        )
                    )
                    db.commit()
                    group = db.execute(
                        select(Group).where(Group.id == group_id)
                    ).scalar()
                    await interaction.followup.send(
                        f"### 登録しました！",
                        ephemeral=True,
                    )

        except Exception as e:
            await interaction.followup.send(
                "エラーが発生しました。再度お試しください。", ephemeral=True
            )
            raise e


def setup(bot):
    return bot.add_cog(ParticipantInfo(bot))
