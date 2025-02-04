import csv
import io
import logging
import re
from datetime import datetime

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

    @slash_command(name="list_participants", description="参加者情報をCSVで表示します")
    async def list_participants(self, ctx: discord.ApplicationContext):
        # Adminに限定
        if not ctx.author.guild_permissions.administrator:
            await ctx.respond(
                "このコマンドはサーバー管理者のみ実行可能です", ephemeral=True
            )
            return

        with get_db() as db:
            participants = db.execute(select(Participant)).scalars().all()

        # csv形式に変換
        # header: id, last_name, first_name, group_id, github_user_name, discord_user_id
        csv_header = "id,last_name,first_name,group_id,github_user_name,discord_user_id"
        csv_body = "\n".join(
            [
                f"{participant.id},{participant.last_name},{participant.first_name},{participant.group_id},{participant.github_user_name},{participant.discord_user_id}"
                for participant in participants
            ]
        )

        csv_data = f"{csv_header}\n{csv_body}"

        # csv_dataを送信
        await ctx.respond(
            "参加者情報をCSVで表示します",
            file=discord.File(
                filename=f"participants_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                fp=io.BytesIO(csv_data.encode())
            ),
            ephemeral=True,
        )

    @slash_command(name="update_participant_info", description="参加者情報を更新します")
    async def update_participant_info(
            self,
            ctx: discord.ApplicationContext,
            user: discord.Option(discord.SlashCommandOptionType.user, "ユーザ"),
            group_id: discord.Option(int, "所属団体ID", default=None),
            last_name: discord.Option(str, "姓（漢字）", default=None),
            first_name: discord.Option(str, "名（漢字）", default=None),
            github_url: discord.Option(str, "GitHubユーザページのURL", default=None),
    ):
        # Adminに限定
        if not ctx.author.guild_permissions.administrator:
            await ctx.respond(
                "このコマンドはサーバー管理者のみ実行可能です", ephemeral=True
            )
            return

        try:
            with get_db() as db:
                # 既存データ取得
                participant = db.execute(
                    select(Participant).where(Participant.discord_user_id == user.id)
                ).scalar()

                if not participant:
                    # 新規作成
                    # 1つでも未入力の場合はエラー
                    if (
                            not last_name
                            or not first_name
                            or not github_url
                            or not group_id
                    ):
                        await ctx.respond(
                            "エラー：新規作成：未入力あり", ephemeral=True
                        )
                        return

                    participant = Participant(
                        last_name=last_name,
                        first_name=first_name,
                        group_id=group_id,
                        github_user_name=github_url,
                        discord_user_id=user.id,
                    )
                    db.add(participant)
                    db.commit()
                    await ctx.respond("新規作成しました", ephemeral=True)
                else:
                    # 更新
                    if last_name:
                        participant.last_name = last_name
                    if first_name:
                        participant.first_name = first_name
                    if github_url:
                        participant.github_user_name = github_url
                    if group_id:
                        participant.group_id = group_id
                    db.add(participant)
                    db.commit()
                    await ctx.respond("更新しました", ephemeral=True)
        except Exception as e:
            await ctx.respond(
                f"エラーが発生しました。再度お試しください。", ephemeral=True
            )
            raise e

    @slash_command(
        name="add_role_for_participants",
        description="登録済み参加者にロールを付与します",
    )
    async def add_role_for_participants(
            self,
            ctx: discord.ApplicationContext,
            role: discord.Option(discord.SlashCommandOptionType.role, "ロール"),
            inverse: discord.Option(
                bool, "非登録ユーザにロールを付与します", default=False
            ),
            target_users_role: discord.Option(
                discord.SlashCommandOptionType.role, "対象ロール", default=None
            ),
    ):
        # Adminに限定
        if not ctx.author.guild_permissions.administrator:
            await ctx.respond(
                "このコマンドはサーバー管理者のみ実行可能です", ephemeral=True
            )
            return

        # 遅延
        await ctx.response.defer(ephemeral=True)

        with get_db() as db:
            participants = db.execute(select(Participant)).scalars().all()
            # 現在の登録済みユーザ
            target_user_ids = [
                participant.discord_user_id for participant in participants
            ]

        if inverse:
            # 非登録ユーザにロールを付与する場合
            all_user_ids = [member.id for member in ctx.guild.members]
            target_user_ids = list(set(all_user_ids) - set(target_user_ids))

        # 対象ロールが指定されている場合
        if target_users_role:
            # 対象ロールが付与されているユーザ
            all_target_user_ids = [member.id for member in target_users_role.members]
            # 登録済みユーザIDと対象ロールが付与されているユーザIDの積集合を取得
            target_user_ids = list(set(target_user_ids) & set(all_target_user_ids))

        # 現在ロールが付与されているユーザ
        assigned_user_ids = [user.id for user in role.members]

        # 新規付与対象
        new_target_user_ids = list(
            set(target_user_ids) - set(assigned_user_ids)
        )  # 対象ユーザに含まれるがロールが付与されていない
        new_target_users = [
            ctx.guild.get_member(user_id) for user_id in new_target_user_ids
        ]

        # ロール削除対象
        remove_target_user_ids = list(
            set(assigned_user_ids) - set(target_user_ids)
        )  # ロールが付与されているが対象ユーザに含まれない
        remove_target_users = [
            ctx.guild.get_member(user_id) for user_id in remove_target_user_ids
        ]

        # ロール付与
        for user in new_target_users:
            if user:
                logging.info(f"add role: {role.name} to {user.display_name}")
                await user.add_roles(role)

        # ロール削除
        for user in remove_target_users:
            if user:
                logging.info(f"remove role: {role.name} from {user.display_name}")
                await user.remove_roles(role)

        await ctx.followup.send("ロールを付与しました", ephemeral=True)

    @slash_command(name="set_nick", description="ユーザのニックネームを設定します")
    async def set_nick(
            self,
            ctx: discord.ApplicationContext,
            format_str: discord.Option(
                str,
                "フォーマット",
                default="[{team}]{last_name} {first_name}_{group_short_name}",
            ),
    ):
        # Adminに限定
        if not ctx.author.guild_permissions.administrator:
            await ctx.respond(
                "このコマンドはサーバー管理者のみ実行可能です", ephemeral=True
            )
            return

        # 遅延
        await ctx.response.defer(ephemeral=True)

        with get_db() as db:
            participants = db.execute(select(Participant)).scalars().all()

            for participant in participants:
                member = ctx.guild.get_member(participant.discord_user_id)

                if not member:
                    continue

                # ロールから"チーム"で始まるものを取得し、その後の文字列を取得
                team = "?"
                for role in member.roles:
                    if role.name.startswith("チーム"):
                        team = role.name.removeprefix("チーム")
                        break

                # フォーマット
                nick = format_str.format(
                    team=team,
                    last_name=participant.last_name,
                    first_name=participant.first_name,
                    group_short_name=participant.group.short_name,
                )

                try:
                    await member.edit(nick=nick)
                except Exception as e:
                    logging.error(f"nick set error: {e}")
                    continue

        await ctx.followup.send("ニックネームを設定しました", ephemeral=True)

    @slash_command(
        name="list_for_modify_role", description="ロール一括修正用のリストを表示します"
    )
    async def list_for_modify_role(
            self,
            ctx: discord.ApplicationContext,
            target_roles_str: discord.Option(
                discord.SlashCommandOptionType.string, "対象ロール", default=None
            ),
    ):
        # Adminに限定
        if not ctx.author.guild_permissions.administrator:
            await ctx.respond(
                "このコマンドはサーバー管理者のみ実行可能です", ephemeral=True
            )
            return

        # 遅延
        await ctx.response.defer(ephemeral=True)

        with get_db() as db:
            participants = db.execute(select(Participant)).scalars().all()

        if target_roles_str:
            # target_roles_strからロールIDを正規表現で取得
            role_ids = re.findall(r"\d+", target_roles_str)
            # ロールIDをintに変換
            role_ids = [int(role_id) for role_id in role_ids]
            roles = []
            for role_id in role_ids:
                role = ctx.guild.get_role(role_id)
                if role:
                    roles.append(role)
        else:
            roles = ctx.guild.roles

        csv_header = (
                "id,last_name,first_name,group_id,github_user_name,discord_user_id,"
                + ",".join(reversed([role.name for role in roles]))
        )
        csv_body_list = []
        for participant in participants:
            member = ctx.guild.get_member(participant.discord_user_id)
            if not member:
                continue

            # ロールが付与されているか
            role_str = ",".join(
                reversed(["1" if role in member.roles else "" for role in roles])
            )

            csv_body = (
                    f"{participant.id},{participant.last_name},{participant.first_name}," +
                    f"{participant.group_id},{participant.github_user_name},{participant.discord_user_id}," +
                    role_str
            )

            csv_body_list.append(csv_body)

        csv_body = "\n".join(csv_body_list)
        csv_data = f"{csv_header}\n{csv_body}"

        await ctx.followup.send(
            "ロール一括修正用のリストを表示します",
            file=discord.File(
                filename=f"modify_roles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                fp=io.BytesIO(csv_data.encode())
            ),
            ephemeral=True,
        )

    @slash_command(
        name="modify_role_from_csv", description="CSVからロールを修正します"
    )
    async def modify_role_from_csv(
            self,
            ctx: discord.ApplicationContext,
    ):
        # Adminに限定
        if not ctx.author.guild_permissions.administrator:
            await ctx.respond(
                "このコマンドはサーバー管理者のみ実行可能です", ephemeral=True
            )
            return

        await ctx.send_modal(ModifyRoleCSVModal(title="ロール一括修正"))


class ModifyRoleCSVModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.add_item(discord.ui.InputText(label="csv", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        # 遅延
        await interaction.response.defer(ephemeral=True)

        # csvデータ取得
        csv_data = self.children[0].value
        csv_lines = csv_data.split("\n")

        # ヘッダー取得
        csv_header = csv_lines[0].split(",")
        # discord_user_idのインデックス取得
        discord_user_id_index = csv_header.index("discord_user_id")
        # discord_user_id_indexの次から最後までをロール名として取得
        role_names = csv_header[(discord_user_id_index + 1):]
        roles = []
        roles_in_guild = {r.name: r for r in interaction.guild.roles}
        for role_name in role_names:
            role = roles_in_guild.get(role_name)
            if role:
                roles.append(role)

        # データ取得
        data = list(csv.DictReader(csv_lines[1:], fieldnames=csv_header))
        logging.info(data)
        logging.info(roles)
        for row in data:
            discord_user_id = int(row["discord_user_id"])
            member = interaction.guild.get_member(discord_user_id)
            if not member:
                continue

            logging.info(f"member: {member.display_name}")

            try:
                for role in roles:
                    if role.name == "@everyone":
                        continue
                    if row[role.name] == "1":
                        logging.info(f"add role: {role.name} to {member.display_name}")
                        await member.add_roles(role)
                    else:
                        logging.info(f"remove role: {role.name} from {member.display_name}")
                        await member.remove_roles(role)
            except discord.Forbidden:
                continue

        await interaction.followup.send("ロールを修正しました", ephemeral=True)


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

                github_user_name = re.search(r"https://github\.com/([^/]+)", github_url).group(1)

                if participant:
                    # 既存の場合は更新
                    participant.last_name = last_name
                    participant.first_name = first_name
                    participant.github_user_name = github_user_name
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
                            github_user_name=github_user_name,
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
