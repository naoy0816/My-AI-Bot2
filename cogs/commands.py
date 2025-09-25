# cogs/commands.py (スラッシュコマンド完全移行版 - タイムアウト対策済み)
import discord
from discord import app_commands
from discord.ext import commands
import json
import google.generativeai as genai
import os
import requests
import io
import time
from PIL import Image, ImageDraw, ImageFont
from . import _utils as utils
from . import _persona_manager as persona_manager
from .ai_chat import load_mood_data
import traceback

# -------------------- ヘルパー関数 --------------------
def load_memory():
    try:
        with open(os.path.join(utils.DATA_DIR, 'bot_memory.json'), 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": []}}

def save_memory(data):
    with open(os.path.join(utils.DATA_DIR, 'bot_memory.json'), 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def load_todos():
    try:
        with open(os.path.join(utils.DATA_DIR, 'todos.json'), 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_todos(data):
    with open(os.path.join(utils.DATA_DIR, 'todos.json'), 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
# ----------------------------------------------------

# ★★★ オーナーだけが使えるコマンドかチェックする関数 ★★★
async def is_owner(interaction: discord.Interaction) -> bool:
    is_owner_check = await interaction.client.is_owner(interaction.user)
    if not is_owner_check:
        try:
            await interaction.response.send_message("このコマンドはオーナー専用よ。アンタには関係ないでしょ？", ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send("このコマンドはオーナー専用よ。アンタには関係ないでしょ？", ephemeral=True)
    return is_owner_check

class UserCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    # ★★★ ヘルプコマンド ★★★
    @app_commands.command(name="help", description="アタシが使えるコマンドの一覧よ♡")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="♡アタシのコマンド一覧♡",
            description="アンタみたいなザコでも使えるように、一覧にしてあげたわ。せいぜい使いこなしなさいよね！",
            color=discord.Color.magenta()
        )
        embed.add_field(name="🧠 AIチャット & 記憶", value="`/remember` `[note]`\n`/recall`\n`/forget` `[index]`\n`/setname` `[name]`\n`/myname`", inline=False)
        embed.add_field(name="🌐 サーバー共通", value="`/server_remember` `[note]`\n`/server_recall`", inline=False)
        embed.add_field(name="👤 ペルソナ管理", value="`/list_personas`\n`/current_persona`\n`/set_persona` `[id]` (オーナー限定)", inline=False)
        embed.add_field(name="🛠️ ツール", value="`/search` `[query]`\n`/todo` `[add/list/done]`\n`/roast` `[image]` `[comment]`\n`/ping`", inline=False)
        embed.add_field(name="⚙️ デバッグ & DB (オーナー限定)", value="`/debug_memory`\n`/backfill_logs` `[limit]`\n`/test_recall` `[query]`\n`/reset_database`\n`/reload_cogs`\n`/db_status`\n`/mood` `[channel]`", inline=False)
        embed.set_footer(text="アタシへの会話は @メンション を付けて話しかけなさいよね！")
        await interaction.response.send_message(embed=embed)

    # ★★★ ペルソナ管理コマンド ★★★
    @app_commands.command(name="list_personas", description="利用可能なペルソナの一覧を表示するわ")
    async def list_personas(self, interaction: discord.Interaction):
        await interaction.response.defer()
        personas = persona_manager.list_personas()
        if not personas:
            await interaction.followup.send("利用できるペルソナが一人もいないんだけど？ `cogs/personas`フォルダを確認しなさい！")
            return
        
        embed = discord.Embed(title="♡アタシがなれる人格（ペルソナ）一覧♡", description="`/set_persona` `[id]`でアタシの人格を変えられるわよ（オーナー限定）", color=discord.Color.gold())
        for p in personas:
            embed.add_field(name=f"**{p['name']}** (`{p['id']}`)", value=p['description'], inline=False)
        
        current_persona_name = utils.get_current_persona().get("name", "不明")
        embed.set_footer(text=f"現在のアタシの人格: {current_persona_name}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="set_persona", description="アタシの人格（ペルソナ）を切り替えるわよ（オーナー限定）")
    @app_commands.describe(persona_id="どのアタシになりたいわけ？IDを指定しなさい！")
    @app_commands.check(is_owner)
    async def set_persona(self, interaction: discord.Interaction, persona_id: str):
        available_personas = [p['id'] for p in persona_manager.list_personas()]
        if persona_id not in available_personas:
            await interaction.response.send_message(f"「{persona_id}」なんて人格、アタシにはないんだけど？ IDが間違ってるんじゃないの？", ephemeral=True)
            return

        memory = load_memory()
        if 'server' not in memory: memory['server'] = {}
        memory['server']['current_persona'] = persona_id
        save_memory(memory)
        
        new_persona = persona_manager.load_persona(persona_id)
        await interaction.response.send_message(f"ふん、しょーがないから、今日からアタシは「**{new_persona.get('name')}**」になってやんよ♡ ありがたく思いなさいよね！")

    @app_commands.command(name="current_persona", description="今のアタシがどんな人格か教えてあげる")
    async def current_persona(self, interaction: discord.Interaction):
        persona = utils.get_current_persona()
        if not persona:
            await interaction.response.send_message("（ごめん、ペルソナファイルがなくて自分が誰だかわかんないの…）", ephemeral=True)
            return
        
        embed = discord.Embed(title=f"♡今のアタシは「{persona.get('name')}」よ♡", description=persona.get('description'), color=discord.Color.green())
        await interaction.response.send_message(embed=embed)

    # ★★★ ツール系コマンド ★★★
    @app_commands.command(name="ping", description="アタシの反応速度を教えてあげるわ")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"しょーがないから教えてあげるわ…アタシの反応速度は **{latency}ms** よ♡")

    @app_commands.command(name="roast", description="画像をイジって生意気なコメント付きで返してあげるわ♡")
    @app_commands.describe(image="イジってほしい画像を添付しなさいよね！", comment="何かアタシに言いたいことでもあるわけ？（任意）")
    async def roast(self, interaction: discord.Interaction, image: discord.Attachment, comment: str = None):
        if not image.content_type or not image.content_type.startswith('image/'):
            await interaction.response.send_message("これ画像じゃないじゃん！ アタシの時間を無駄にさせないでくれる？", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            roast_model = genai.GenerativeModel('gemini-1.5-pro')
            img_data = await image.read()
            img = Image.open(io.BytesIO(img_data)).convert("RGBA")
            roast_prompt = f"""
あなたは、ユーザーが投稿した画像に、生意気で面白いコメントを入れる天才美少女「メスガキちゃん」です。
ユーザーからの指示: {comment or "（特になし）"}
あなたが書き込む辛口コメント（1文だけ）:
"""
            roast_response = await roast_model.generate_content_async(roast_prompt)
            roast_text = roast_response.text.strip().replace('。', '')
            draw = ImageDraw.Draw(img)
            font_size = int(min(img.width, img.height) * 0.1)
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()
            try:
                bbox = draw.textbbox((0, 0), roast_text, font=font)
                text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except TypeError:
                text_width, text_height = draw.textsize(roast_text, font=font)
            x = img.width - text_width - int(img.width * 0.05)
            y = img.height - text_height - int(img.height * 0.05)
            shadow_color="white"
            draw.text((x-2, y-2), roast_text, font=font, fill=shadow_color)
            draw.text((x+2, y-2), roast_text, font=font, fill=shadow_color)
            draw.text((x-2, y+2), roast_text, font=font, fill=shadow_color)
            draw.text((x+2, y+2), roast_text, font=font, fill=shadow_color)
            draw.text((x, y), roast_text, font=font, fill="black")
            final_buffer = io.BytesIO()
            img.save(final_buffer, format='PNG')
            final_buffer.seek(0)
            await interaction.followup.send(file=discord.File(final_buffer, 'roast.png'))
        except Exception as e:
            await interaction.followup.send(f"（うぅ…画像の処理中にエラーが出たわ…: {e}）")

    @app_commands.command(name="search", description="ペルソナを反映してWeb検索するわよ")
    @app_commands.describe(query="何をググってほしいわけ？")
    async def search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        persona = utils.get_current_persona()
        if not persona:
            await interaction.followup.send("（ごめん、ペルソナファイルが読み込めないの…）", ephemeral=True)
            return
        
        search_results = utils.google_search(query)
        if isinstance(search_results, str) or not search_results:
            await interaction.followup.send(search_results or "（何も見つからなかったわ。）")
            return
        
        search_results_text = "\n\n".join([f"【ソース: {item.get('displayLink')}】{item.get('title')}\n{item.get('snippet')}" for item in search_results])
        char_settings = persona["settings"].get("char_settings", "").format(user_name=interaction.user.display_name)
        search_prompt_template = persona["settings"].get("search_prompt", "# 指示\n検索結果を元に応答しなさい。")
        synthesis_prompt = f"{char_settings}\n{search_prompt_template}\n# 検索結果\n{search_results_text}\n# ユーザーの質問\n{query}\n# あなたの回答:"
        try:
            response = await self.model.generate_content_async(synthesis_prompt)
            await interaction.followup.send(response.text)
        except Exception as e: 
            await interaction.followup.send(f"（頭脳がショートしたわ…: {e}）")

    # ★★★ TODOコマンドグループ ★★★
    todo_group = app_commands.Group(name="todo", description="アンタがやるべきことを管理してあげる♡")

    @todo_group.command(name="add", description="やることをリストに追加してやんよ")
    @app_commands.describe(task="追加する内容をちゃんと書きなさいよね！")
    async def todo_add(self, interaction: discord.Interaction, task: str):
        user_id = str(interaction.user.id)
        todos = load_todos()
        if user_id not in todos: todos[user_id] = []
        todos[user_id].append(task)
        save_todos(todos)
        await interaction.response.send_message(f"しょーがないから「{task}」をアンタのリストに追加してやんよ♡")

    @todo_group.command(name="list", description="アンタのやる事リストを見せてあげる")
    async def todo_list(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        todos = load_todos()
        if user_id not in todos or not todos[user_id]:
            await interaction.response.send_message('アンタのやる事リストは空っぽよw')
        else:
            list_text = "\n".join([f"{i+1}. {t}" for i, t in enumerate(todos[user_id])])
            await interaction.response.send_message(f"アンタがやるべきことリストよ♡\n{list_text}")

    @todo_group.command(name="done", description="完了したことをリストから消してあげる")
    @app_commands.describe(index="消したいタスクの番号をちゃんと指定しなさいよね！")
    async def todo_done(self, interaction: discord.Interaction, index: int):
        user_id = str(interaction.user.id)
        todos = load_todos()
        if user_id not in todos or not todos[user_id]:
            await interaction.response.send_message('アンタのやる事リストは空っぽよw', ephemeral=True)
            return
        real_index = index - 1
        if 0 <= real_index < len(todos[user_id]):
            removed = todos[user_id].pop(real_index)
            save_todos(todos)
            await interaction.response.send_message(f"「{removed}」を消してあげたわよ。上出来じゃん？♡")
        else:
            await interaction.response.send_message('その番号のタスクなんてないわよ。', ephemeral=True)
            
    # ★★★ 記憶管理コマンド ★★★
    @app_commands.command(name="remember", description="アタシにアンタのことを記憶させる")
    @app_commands.describe(note="アタシに何を覚えてほしいわけ？")
    async def remember(self, interaction: discord.Interaction, note: str):
        await interaction.response.defer()
        embedding = await utils.get_embedding(note)
        if embedding is None:
            await interaction.followup.send("（エラーで脳に刻み込めなかったわ…）", ephemeral=True)
            return
        memory = load_memory()
        user_id = str(interaction.user.id)
        if user_id not in memory['users']: memory['users'][user_id] = {'notes': []}
        if not any(n['text'] == note for n in memory['users'][user_id]['notes']):
            memory['users'][user_id]['notes'].append({'text': note, 'embedding': embedding})
            save_memory(memory)
            await interaction.followup.send(f"ふーん、「{note}」ね。覚えててやんよ♡")
        else:
            await interaction.followup.send("それ、もう知ってるし。", ephemeral=True)

    @app_commands.command(name="recall", description="アタシがアンタについて覚えてることリストよ♡")
    async def recall(self, interaction: discord.Interaction):
        memory = load_memory()
        user_id = str(interaction.user.id)
        user_notes = memory.get('users', {}).get(user_id, {}).get('notes', [])
        if not user_notes:
            await interaction.response.send_message('アンタに関する記憶は、まだ何もないけど？w')
        else:
            notes_text = "\n".join([f"{i+1}. {n['text']}" for i, n in enumerate(user_notes)])
            await interaction.response.send_message(f"アタシがアンタについて覚えてることリストよ♡\n{notes_text}")

    @app_commands.command(name="forget", description="アンタに関する記憶を忘れさせてあげる")
    @app_commands.describe(index="消したい記憶の番号をちゃんと指定しなさいよね！")
    async def forget(self, interaction: discord.Interaction, index: int):
        memory = load_memory()
        user_id = str(interaction.user.id)
        real_index = index - 1
        if user_id in memory['users'] and 0 <= real_index < len(memory['users'][user_id].get('notes', [])):
            removed = memory['users'][user_id]['notes'].pop(real_index)
            save_memory(memory)
            await interaction.response.send_message(f"「{removed['text']}」ね。アンタの記憶から消してあげたわよ。")
        else:
            await interaction.response.send_message('その番号の記憶なんて、元からないんだけど？', ephemeral=True)

    @app_commands.command(name="setname", description="アタシが呼ぶアンタの名前を設定する")
    @app_commands.describe(name="これからは、なんて呼んでやろうかしら？♡")
    async def setname(self, interaction: discord.Interaction, name: str):
        memory = load_memory()
        user_id = str(interaction.user.id)
        if user_id not in memory.get('users', {}): memory['users'][user_id] = {'notes': []}
        memory['users'][user_id]['fixed_nickname'] = name
        save_memory(memory)
        await interaction.response.send_message(f"ふん、アンタのこと、これからは「{name}」って呼んでやんよ♡")

    @app_commands.command(name="myname", description="アタシがアンタをなんて呼んでるか確認しなさいよね")
    async def myname(self, interaction: discord.Interaction):
        memory = load_memory()
        user_id = str(interaction.user.id)
        nickname = memory.get('users', {}).get(user_id, {}).get('fixed_nickname')
        if nickname:
            await interaction.response.send_message(f"アンタの名前は「{nickname}」でしょ？♡")
        else:
            await interaction.response.send_message(f"アンタ、まだ名前を教えてないじゃない。`/setname`で教えなさい！")
            
    # ★★★ デバッグ系コマンド (オーナー限定) ★★★
    @app_commands.command(name="reload_cogs", description="アタシの機能を全部リロードするわよ（オーナー限定）")
    @app_commands.check(is_owner)
    async def reload_cogs(self, interaction: discord.Interaction):
        await interaction.response.defer()
        loaded_cogs, failed_cogs = [], []
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('_'):
                cog_name = f'cogs.{filename[:-3]}'
                try:
                    await self.bot.reload_extension(cog_name)
                    loaded_cogs.append(f"`{filename}`")
                except commands.ExtensionNotLoaded:
                    await self.bot.load_extension(cog_name)
                    loaded_cogs.append(f"`{filename}` (新規)")
                except Exception as e:
                    failed_cogs.append(f"`{filename}` ({e})")
        response = "機能の再読み込みが完了したわよ♡\n"
        if loaded_cogs: response += f"✅ **成功:** {', '.join(loaded_cogs)}\n"
        if failed_cogs: response += f"❌ **失敗:** {', '.join(failed_cogs)}"
        await interaction.followup.send(response)

    @app_commands.command(name="backfill_logs", description="サーバーの過去ログをDBに保存するわ（オーナー限定）")
    @app_commands.describe(limit="各チャンネルから最大何件取得する？（デフォルト: 100）")
    @app_commands.check(is_owner)
    async def backfill_logs(self, interaction: discord.Interaction, limit: int = 100):
        await interaction.response.defer()
        db_manager = self.bot.get_cog('DatabaseManager')
        if not db_manager or not db_manager.chroma_client:
            await interaction.followup.send("（ごめん、データベースマネージャーが準備できてないみたい…）", ephemeral=True)
            return
        
        start_time = time.time()
        total_processed, total_added = 0, 0
        text_channels = [ch for ch in interaction.guild.text_channels if ch.permissions_for(interaction.guild.me).read_message_history]
        for channel in text_channels:
            try:
                async for message in channel.history(limit=limit):
                    total_processed += 1
                    if await db_manager.add_message_to_db(message):
                        total_added += 1
            except Exception as e:
                print(f"Error backfilling channel {channel.name}: {e}")
        duration = round(time.time() - start_time, 2)
        await interaction.followup.send(f"過去ログ学習、完了！\n**処理:** {total_processed}件, **新規追加:** {total_added}件, **時間:** {duration}秒")

    @app_commands.command(name="mood", description="チャンネルのムード状況を表示するわ（オーナー限定）")
    @app_commands.describe(channel="どのチャンネルのムードが知りたいわけ？（任意）")
    @app_commands.check(is_owner)
    async def mood_command(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target_channel = channel or interaction.channel
        channel_mood = load_mood_data().get(str(target_channel.id))
        if not channel_mood:
            await interaction.response.send_message(f"#{target_channel.name} のムードデータはまだ記録されてないみたいね。", ephemeral=True); return
        avg_score = channel_mood.get("average", 0.0)
        mood_text, color = ("😐 ニュートラル", discord.Color.default())
        if avg_score > 0.2: mood_text, color = "😊 ポジティブ", discord.Color.green()
        elif avg_score < -0.2: mood_text, color = "😠 ネガティブ", discord.Color.red()
        embed = discord.Embed(title=f"🧠 #{target_channel.name} のムード分析 🧠", description=f"現在の雰囲気: **{mood_text}**", color=color)
        embed.add_field(name="平均ムードスコア", value=f"`{avg_score:.4f}`", inline=True)
        embed.add_field(name="記録スコア数", value=f"`{len(channel_mood.get('scores', []))}`件 / 直近10件", inline=True)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(UserCommands(bot))
