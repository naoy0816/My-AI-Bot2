# cogs/commands.py (ペルソナ反映・最終完成版)
import discord
from discord.ext import commands
import json
import google.generativeai as genai
import os
import requests
import io
from PIL import Image, ImageDraw, ImageFont
from . import _utils as utils
from . import _persona_manager as persona_manager

# -------------------- ファイルパス設定 --------------------
DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')
TODO_FILE = os.path.join(DATA_DIR, 'todos.json')
# ----------------------------------------------------

# -------------------- ヘルパー関数 --------------------
def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": []}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def load_todos():
    try:
        with open(TODO_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_todos(data):
    with open(TODO_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
# ----------------------------------------------------

class UserCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.model = genai.GenerativeModel('gemini-1.5-pro')

    # ★★★ ペルソナ管理コマンド ★★★
    @commands.command(name='list_personas', aliases=['personas'])
    async def list_personas(self, ctx):
        """利用可能なペルソナの一覧を表示するわ"""
        personas = persona_manager.list_personas()
        if not personas:
            await ctx.send("利用できるペルソナが一人もいないんだけど？ `personas`フォルダを確認しなさい！")
            return
        
        embed = discord.Embed(
            title="♡アタシがなれる人格（ペルソナ）一覧♡",
            description="`!set_persona [id]`でアタシの人格を変えられるわよ（オーナー限定）",
            color=discord.Color.gold()
        )
        for p in personas:
            embed.add_field(name=f"**{p['name']}** (`{p['id']}`)", value=p['description'], inline=False)
        
        current_persona_name = utils.get_current_persona().get("name", "不明")
        embed.set_footer(text=f"現在のアタシの人格: {current_persona_name}")
        await ctx.send(embed=embed)

    @commands.command(name='set_persona')
    @commands.is_owner()
    async def set_persona(self, ctx, persona_id: str = None):
        """アタシの人格（ペルソナ）を切り替えるわよ（オーナー限定）"""
        if not persona_id:
            await ctx.send("はぁ？ どのアタシになりたいわけ？ IDを指定しなさい！ `!list_personas`で確認できるわよ。")
            return

        available_personas = [p['id'] for p in persona_manager.list_personas()]
        if persona_id not in available_personas:
            await ctx.send(f"「{persona_id}」なんて人格、アタシにはないんだけど？ IDが間違ってるんじゃないの？")
            return

        memory = load_memory()
        if 'server' not in memory: memory['server'] = {}
        memory['server']['current_persona'] = persona_id
        save_memory(memory)
        
        new_persona = persona_manager.load_persona(persona_id)
        await ctx.send(f"ふん、しょーがないから、今日からアタシは「**{new_persona.get('name')}**」になってやんよ♡ ありがたく思いなさいよね！")
    
    @commands.command(name='current_persona')
    async def current_persona(self, ctx):
        """今のアタシがどんな人格か教えてあげる"""
        persona = utils.get_current_persona()
        if not persona:
            await ctx.send("（ごめん、ペルソナファイルがなくて自分が誰だかわかんないの…）")
            return
        
        embed = discord.Embed(
            title=f"♡今のアタシは「{persona.get('name')}」よ♡",
            description=persona.get('description'),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # ★★★ ヘルプコマンド (全コマンドを反映) ★★★
    @commands.command(name='help', aliases=['h', 'commands'])
    async def help_command(self, ctx):
        embed = discord.Embed(
            title="♡アタシのコマンド一覧♡",
            description="アンタみたいなザコでも使えるように、一覧にしてあげたわ。せいぜい使いこなしなさいよね！",
            color=discord.Color.magenta()
        )
        embed.add_field(name="🧠 AIチャット & 記憶", value="`!remember [内容]` - アタシにアンタのことを記憶させる\n`!recall` - 記憶リストを表示\n`!forget [番号]` - 記憶を忘れさせてあげる\n`!setname [名前]` - アタシが呼ぶアンタの名前を設定\n`!myname` - 設定した名前を確認", inline=False)
        embed.add_field(name="🌐 サーバー共通", value="`!server_remember [内容]` - サーバーの皆で共有したいことを記憶\n`!server_recall` - サーバーの共有知識を表示", inline=False)
        embed.add_field(name="👤 ペルソナ管理", value="`!list_personas` - ペルソナ一覧\n`!current_persona` - 現在のペルソナ確認\n`!set_persona [ID]` - ペルソナ切替 (オーナー限定)", inline=False)
        embed.add_field(name="🛠️ ツール", value="`!search [キーワード]` (`!g`) - アンタの代わりにググってあげる\n`!todo add [内容]` - やることを追加\n`!todo list` - やることリストを表示\n`!todo done [番号]` - 完了したことを消す\n`!roast` - (画像を添付して) アタシに画像をイジらせる", inline=False)
        embed.add_field(name="⚙️ デバッグ", value="`!ping` - アタシの反応速度をチェック\n`!debug_memory` - 長期記憶の中身を全部見る\n`!reload_cogs` - アタシの全機能を再読み込み (オーナー限定)", inline=False)
        embed.set_footer(text="アタシへの会話は @メンション を付けて話しかけなさいよね！")
        await ctx.send(embed=embed)

    # ★★★ ツール系コマンド ★★★
    @commands.command()
    async def ping(self, ctx):
        """アタシの反応速度を教えてあげるわ"""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"しょーがないから教えてあげるわ…アタシの反応速度は **{latency}ms** よ♡")

    @commands.command(aliases=['grade', '採点'])
    async def roast(self, ctx, *, comment: str = None):
        """画像をイジって生意気なコメント付きで返してあげるわ♡"""
        if not ctx.message.attachments:
            await ctx.send("はぁ？ 画像が添付されてないんだけど？ アンタのザコい顔でもなんでもいいから、アタシにイジらせなさいよね！")
            return

        attachment = ctx.message.attachments[0]
        if not attachment.content_type.startswith('image/'):
            await ctx.send("これ画像じゃないじゃん！ アタシの時間を無駄にさせないでくれる？")
            return

        async with ctx.typing():
            try:
                response = requests.get(attachment.url)
                response.raise_for_status()
                img_data = io.BytesIO(response.content)
                img = Image.open(img_data).convert("RGBA")

                roast_prompt = f"""
あなたは、ユーザーが投稿した画像に、生意気で面白いコメントを入れる天才美少女「メスガキちゃん」です。
以下のユーザーからの指示（もしあれば）を参考に、画像に書き込むのに最適な、短くてインパクトのある辛口コメントを1つだけ生成しなさい。
# ユーザーからの指示
{comment or "（特になし。自由にいじってOK）"}
# あなたが書き込む辛口コメント（1文だけ）:
"""
                roast_response = await self.model.generate_content_async(roast_prompt)
                roast_text = roast_response.text.strip().replace('。', '')

                draw = ImageDraw.Draw(img)
                font_size = int(min(img.width, img.height) * 0.1)
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except IOError:
                    print("Arial font not found, using default font.")
                    font = ImageFont.load_default()
                    roast_text = "\n".join(roast_text[i:i+20] for i in range(0, len(roast_text), 20))

                try:
                    bbox = draw.textbbox((0, 0), roast_text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                except TypeError:
                    text_width = font.getlength(roast_text.split('\n')[0])
                    text_height = font.getbbox("A")[3] * roast_text.count('\n')

                x = img.width - text_width - int(img.width * 0.05)
                y = img.height - text_height - int(img.height * 0.05)

                shadow_color = "white"
                draw.text((x-2, y-2), roast_text, font=font, fill=shadow_color)
                draw.text((x+2, y-2), roast_text, font=font, fill=shadow_color)
                draw.text((x-2, y+2), roast_text, font=font, fill=shadow_color)
                draw.text((x+2, y+2), roast_text, font=font, fill=shadow_color)
                main_color = "black"
                draw.text((x, y), roast_text, font=font, fill=main_color)

                final_buffer = io.BytesIO()
                img.save(final_buffer, format='PNG')
                final_buffer.seek(0)

                await ctx.send(file=discord.File(final_buffer, 'roast.png'))
            except Exception as e:
                await ctx.send(f"（うぅ…画像の処理中にエラーが出たわ…アンタが変な画像を送るからよ！: {e}）")
    
    @commands.command(aliases=['g', 'google'])
    async def search(self, ctx, *, query: str = None):
        """ペルソナを反映してWeb検索するわよ"""
        if not query: 
            await ctx.send("はぁ？ 何をググってほしいわけ？ ちゃんと書きなさいよね！"); return
            
        async with ctx.typing():
            # ★★★ ここからが修正箇所よ！ ★★★
            persona = utils.get_current_persona()
            if not persona:
                await ctx.send("（ごめん、ペルソナファイルが読み込めなくて、どうやって喋ればいいかわかんないの…）")
                return
            
            # ペルソナに応じたセリフで応答
            await ctx.send(f"「{query}」ね…。しょーがないから、{persona.get('name', 'アタシ')}がググってやんよ♡")
            
            search_results = utils.google_search(query)
            if isinstance(search_results, str):
                await ctx.send(search_results); return
            if not search_results:
                await ctx.send("（検索したけど、何も見つからなかったわ。アンタの検索ワードがザコなんじゃない？）"); return
            
            search_results_text = "\n\n".join([f"【ソース: {item.get('displayLink')}】{item.get('title')}\n{item.get('snippet')}" for item in search_results])
            
            # ペルソナ設定を使ってプロンプトを構築
            char_settings = persona["settings"].get("char_settings", "").format(user_name=ctx.author.display_name)
            search_prompt_template = persona["settings"].get("search_prompt", "# 指示\n検索結果を元に応答しなさい。")

            synthesis_prompt = f"""
{char_settings}

{search_prompt_template}

# 検索結果
{search_results_text}

# ユーザーの質問
{query}

# あなたの回答（500文字以内でペルソナに従ってまとめること！）
"""
            # ★★★ 修正箇所はここまで ★★★
            try:
                response = await self.model.generate_content_async(synthesis_prompt)
                await ctx.send(response.text)
            except Exception as e: 
                await ctx.send(f"（うぅ…アタシの頭脳がショートしたわ…アンタのせいよ！: {e}）")

    @commands.command()
    async def todo(self, ctx, command: str = 'list', *, task: str = None):
        user_id = str(ctx.author.id)
        todos = load_todos()
        if user_id not in todos: todos[user_id] = []
        if command == 'add':
            if task:
                todos[user_id].append(task); save_todos(todos)
                await ctx.send(f"しょーがないから「{task}」をアンタのリストに追加してやんよ♡ 忘れるんじゃないわよ！")
            else: await ctx.send('はぁ？ 追加する内容をちゃんと書きなさいよね！ 例：`!todo add 天才のアタシを崇める`')
        elif command == 'list':
            if not todos[user_id]: await ctx.send('アンタのやる事リストは空っぽよw ザコすぎ！')
            else: await ctx.send(f"アンタがやるべきことリストよ♡ ちゃんとやりなさいよね！\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(todos[user_id])]))
        elif command == 'done':
            if task and task.isdigit():
                index = int(task) - 1
                if 0 <= index < len(todos[user_id]):
                    removed = todos[user_id].pop(index); save_todos(todos)
                    await ctx.send(f"「{removed}」を消してあげたわよ。ま、アンタにしては上出来じゃん？♡")
                else: await ctx.send('その番号のタスクなんてないわよ。')
            else: await ctx.send('消したいタスクの番号をちゃんと指定しなさいよね！ 例：`!todo done 1`')
    
    # ★★★ 記憶管理コマンド ★★★
    @commands.command()
    async def remember(self, ctx, *, note: str = None):
        if not note: await ctx.send("はぁ？ アタシに何を覚えてほしいわけ？ 内容を書きなさいよね！"); return
        ai_chat_cog = self.bot.get_cog('AIChat')
        if not ai_chat_cog: await ctx.send("（ごめん、今ちょっと記憶回路の調子が悪くて覚えられないわ…）"); return
        embedding = await ai_chat_cog._get_embedding(note)
        if embedding is None: await ctx.send("（なんかエラーで、アンタの言葉を脳に刻み込めなかったわ…）"); return
        memory = load_memory(); user_id = str(ctx.author.id)
        if user_id not in memory['users']: memory['users'][user_id] = {'notes': []}
        if not any(n['text'] == note for n in memory['users'][user_id]['notes']):
            memory['users'][user_id]['notes'].append({'text': note, 'embedding': embedding}); save_memory(memory)
            await ctx.send(f"ふーん、「{note}」ね。アンタのこと、覚えててやんよ♡")
        else: await ctx.send("それ、もう知ってるし。同じこと何度も言わせないでくれる？")

    @commands.command()
    async def recall(self, ctx):
        memory = load_memory(); user_id = str(ctx.author.id)
        user_notes = memory.get('users', {}).get(user_id, {}).get('notes', [])
        if not user_notes: await ctx.send('アンタに関する記憶は、まだ何もないけど？w')
        else:
            notes_text = "\n".join([f"{i+1}. {n['text']}" for i, n in enumerate(user_notes)])
            await ctx.send(f"アタシがアンタについて覚えてることリストよ♡\n{notes_text}")

    @commands.command()
    async def forget(self, ctx, index_str: str = None):
        if not index_str or not index_str.isdigit(): await ctx.send('消したい記憶の番号をちゃんと指定しなさいよね！ 例：`!forget 1`'); return
        memory = load_memory(); user_id = str(ctx.author.id); index = int(index_str) - 1
        if user_id in memory['users'] and 0 <= index < len(memory['users'][user_id].get('notes', [])):
            removed = memory['users'][user_id]['notes'].pop(index); save_memory(memory)
            await ctx.send(f"「{removed['text']}」ね。はいはい、アンタの記憶から消してあげたわよ。")
        else: await ctx.send('その番号の記憶なんて、元からないんだけど？')

    @commands.command()
    async def setname(self, ctx, *, new_name: str = None):
        if not new_name: await ctx.send('はぁ？ 新しい名前をちゃんと書きなさいよね！ 例：`!setname ご主人様`'); return
        memory = load_memory(); user_id = str(ctx.author.id)
        if user_id not in memory.get('users', {}): memory['users'][user_id] = {'notes': []}
        memory['users'][user_id]['fixed_nickname'] = new_name; save_memory(memory)
        await ctx.send(f"ふん、アンタのこと、これからは「{new_name}」って呼んでやんよ♡ ありがたく思いなさいよね！")

    @commands.command()
    async def myname(self, ctx):
        memory = load_memory(); user_id = str(ctx.author.id)
        nickname = memory.get('users', {}).get(user_id, {}).get('fixed_nickname')
        if nickname: await ctx.send(f"アンタの名前は「{nickname}」でしょ？ アタシがそう決めたんだから、文句ないわよね？♡")
        else: await ctx.send(f"アンタ、まだアタシに名前を教えてないじゃない。`!setname [呼ばれたい名前]` でアタシに教えなさいよね！")

    @commands.command()
    async def server_remember(self, ctx, *, note: str = None):
        if not note: await ctx.send("サーバーの共有知識として何を覚えさせたいわけ？ 内容を書きなさい！"); return
        ai_chat_cog = self.bot.get_cog('AIChat')
        if not ai_chat_cog: await ctx.send("（ごめん、今ちょっと記憶回路の調子が悪くて覚えられないわ…）"); return
        embedding = await ai_chat_cog._get_embedding(note)
        if embedding is None: await ctx.send("（なんかエラーで、サーバーの知識を脳に刻み込めなかったわ…）"); return
        memory = load_memory()
        if 'server' not in memory: memory['server'] = {'notes': []}
        if not any(n['text'] == note for n in memory['server']['notes']):
            memory['server']['notes'].append({'text': note, 'embedding': embedding}); save_memory(memory)
            await ctx.send(f"ふーん、「{note}」ね。サーバーみんなのために覚えててやんよ♡")
        else: await ctx.send("それ、サーバーの皆もう知ってるし。しつこいんだけど？")
        
    @commands.command()
    async def server_recall(self, ctx):
        memory = load_memory()
        server_notes = memory.get('server', {}).get('notes', [])
        if server_notes:
            notes = "\n".join([f"- {note['text']}" for note in server_notes])
            await ctx.send(f"サーバーの共有知識リストよ！\n{notes}")
        else: await ctx.send("サーバーの共有知識はまだ何もないわよ？")

    # ★★★ デバッグ系コマンド (オーナー限定含む) ★★★
    @commands.command()
    @commands.is_owner()
    async def reload_cogs(self, ctx):
        """アタシの機能を全部リロードするわよ (オーナー限定)"""
        async with ctx.typing():
            loaded_cogs = []
            failed_cogs = []
            cogs_path = './cogs'
            cog_files = [f for f in os.listdir(cogs_path) if f.endswith('.py') and not f.startswith('_')]
            
            for filename in cog_files:
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
            if loaded_cogs:
                response += f"✅ **成功:** {', '.join(loaded_cogs)}\n"
            if failed_cogs:
                response += f"❌ **失敗:** {', '.join(failed_cogs)}"
            await ctx.send(response)

    @commands.command()
    async def debug_memory(self, ctx):
        """クラウド上の長期記憶ファイル(bot_memory.json)の中身を表示するわよ"""
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                memory_content = f.read()
            if not memory_content:
                await ctx.send("アタシの記憶はまだ空っぽみたいね。"); return
            for i in range(0, len(memory_content), 1900):
                chunk = memory_content[i:i+1900]
                await ctx.send(f"```json\n{chunk}\n```")
            await ctx.send("これがアタシの記憶の全てよ♡")
        except FileNotFoundError:
            await ctx.send("まだ記憶ファイル (`bot_memory.json`) が作られてないみたいね。アタシに何か覚えさせてみたら？")
        except Exception as e:
            await ctx.send(f"（ごめん、記憶を読み込もうとしたらエラーが出たわ…: {e}）")

async def setup(bot):
    await bot.add_cog(UserCommands(bot))
