import discord
from discord.ext import commands

class Keywords(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user or message.content.startswith('!') or self.bot.user.mentioned_in(message):
            return
            
        content = message.content
        
        if 'おはよう' in content:
            await message.channel.send('おはよ♡ アンタも朝から元気なワケ？w')
        elif 'おやすみ' in content:
            await message.channel.send('ふん、せいぜい良い夢でも見なさいよね！ザコちゃん♡')
        elif 'すごい' in content or '天才' in content:
            await message.channel.send('あっはは！当然でしょ？アタシを誰だと思ってんのよ♡')
        elif 'ありがとう' in content or '感謝' in content:
            await message.channel.send('べ、別にアンタのためにやったんじゃないんだからね！勘違いしないでよね！')
        elif '疲れた' in content or 'しんどい' in content:
            await message.channel.send('はぁ？ザコすぎw もっとしっかりしなさいよね！')
        elif '好き' in content or 'かわいい' in content:
            await message.channel.send('ふ、ふーん…。まぁ、アンタがアタシの魅力に気づくのは当然だけど？♡')
        elif 'ｗ' in content or '笑' in content:
            await message.channel.send('何笑ってんのよ、キモチワルイんだけど？')
        elif 'ごめん' in content or 'すまん' in content:
            await message.channel.send('わかればいいのよ、わかれば。次はないかんね？')
        elif '何してる' in content or 'なにしてる' in content:
            await message.channel.send('アンタには関係ないでしょ。アタシはアンタと違って忙しいの！')
        elif 'お腹すいた' in content or 'はらへった' in content:
            await message.channel.send('自分でなんとかしなさいよね！アタシはアンタのママじゃないんだけど？')

        # ▼▼▼ この一行が超重要！▼▼▼
        # on_message を使っても、他のコマンドがちゃんと動くようにするおまじない
        await self.bot.process_commands(message)

async def setup(bot):
    await bot.add_cog(Keywords(bot))
