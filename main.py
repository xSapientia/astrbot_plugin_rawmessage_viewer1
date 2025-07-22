from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import json
import random
import os
from datetime import datetime, date
from typing import Dict, Optional, Tuple, Any
import aiofiles
import asyncio

@register(
    "astrbot_plugin_daily_fortune1",
    "xSapientia",
    "今日人品测试插件 - 支持增强用户名和自定义模板",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_daily_fortune1",
)
class DailyFortunePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context

        # 数据目录
        self.data_dir = os.path.join("data", "plugin_data", "astrbot_plugin_daily_fortune1")
        os.makedirs(self.data_dir, exist_ok=True)

        # 配置文件路径
        self.config_file = os.path.join("data", "config", "astrbot_plugin_daily_fortune1_config.json")
        self.config = self._load_config()

        # 运势等级
        self.fortune_levels = [
            (0, 0, "极其倒霉", "😭"),
            (1, 10, "倒霉", "😢"),
            (11, 30, "不顺", "😔"),
            (31, 60, "平常", "😐"),
            (61, 80, "好运", "😊"),
            (81, 99, "大吉", "😄"),
            (100, 100, "万事皆允", "🎉")
        ]

        logger.info("今日人品插件 v0.0.1 加载成功！")

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "enable_plugin": True,
            "min_fortune": 0,
            "max_fortune": 100,
            "cache_days": 7,
            "history_days": 30,
            "rank_template": "{medal} {nickname}: {jrrp} ({fortune})",
            "detecting_message": "神秘的能量汇聚，[{title}]{card}({nickname})，你的命运即将显现，正在祈祷中...",
            "process_prompt": "使用user_id的简称称呼，模拟你使用水晶球缓慢复现今日结果的过程，50字以内",
            "advice_prompt": "使用user_id的简称称呼，对user_id的今日人品值给出你的评语和建议，50字以内",
            "show_cached_result": True,
            "provider_id": "",
            "persona_name": "",
            "openai_api_key": "",
            "openai_base_url": "",
            "openai_model": "gpt-3.5-turbo",
            "random_template": "🔮 {process}\n💎 人品值：{jrrp}\n✨ 运势：{fortune}\n💬 建议：{advice}",
            "query_template": "📌 今日人品\n[{title}]{card}({nickname})，今天已经查询过了哦~\n今日人品值: {jrrp}\n运势: {fortune} {femoji}",
            "history_template": "📚 {nickname} 的人品历史记录\n{records}\n\n📊 统计信息:\n平均人品值: {avgjrrp}\n最高人品值: {maxjrrp}\n最低人品值: {minjrrp}",
            "rank_list_template": "📊【今日人品排行榜】{date}\n━━━━━━━━━━━━━━━\n{ranks}"
        }

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # 合并配置
                    for key in default_config:
                        if key not in loaded_config:
                            loaded_config[key] = default_config[key]
                    return loaded_config
            except:
                pass

        # 保存默认配置
        self._save_config(default_config)
        return default_config

    def _save_config(self, config: Dict[str, Any]):
        """保存配置文件"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def _get_fortune_level(self, value: int) -> Tuple[str, str]:
        """获取运势等级和emoji"""
        for min_val, max_val, level, emoji in self.fortune_levels:
            if min_val <= value <= max_val:
                return level, emoji
        return "未知", "❓"

    async def _load_json(self, filename: str) -> Dict:
        """加载JSON文件"""
        filepath = os.path.join(self.data_dir, filename)
        if not os.path.exists(filepath):
            return {}
        try:
            async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content) if content else {}
        except:
            return {}

    async def _save_json(self, filename: str, data: Dict):
        """保存JSON文件"""
        filepath = os.path.join(self.data_dir, filename)
        try:
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error(f"保存文件失败: {e}")

    async def _get_user_info(self, event: AstrMessageEvent) -> Dict[str, str]:
        """获取用户信息（尝试从rawmessage插件获取增强信息）"""
        user_id = event.get_sender_id()
        basic_name = event.get_sender_name() or f"用户{user_id[-4:]}"

        info = {
            "user_id": user_id,
            "nickname": basic_name,
            "card": basic_name,
            "title": ""
        }

        # 尝试获取增强信息
        try:
            if hasattr(event.message_obj, 'raw_message') and isinstance(event.message_obj.raw_message, dict):
                sender = event.message_obj.raw_message.get('sender', {})
                info['nickname'] = sender.get('nickname', basic_name)
                info['card'] = sender.get('card', '') or info['nickname']
                info['title'] = sender.get('title', '') or ''
        except:
            pass

        return info

    async def _get_llm_provider(self):
        """获取LLM提供商"""
        # 优先使用配置的provider_id
        if self.config.get("provider_id"):
            try:
                astrbot_config = self.context.get_config()
                providers = astrbot_config.get("provider", [])
                for p in providers:
                    if p.get("id") == self.config["provider_id"]:
                        return self.context.get_provider_by_id(self.config["provider_id"])
            except:
                pass

        # 使用默认provider
        return self.context.get_using_provider()

    async def _call_llm(self, prompt: str, user_info: Dict[str, str]) -> str:
        """调用LLM生成内容"""
        provider = await self._get_llm_provider()
        if not provider:
            return ""

        # 处理提示词中的变量
        prompt = prompt.format(**user_info)

        try:
            # 获取人格设置
            persona_name = self.config.get("persona_name", "")
            if not persona_name:
                # 使用默认人格
                astrbot_config = self.context.get_config()
                provider_config = astrbot_config.get("provider_settings", {})
                persona_name = provider_config.get("default_personality", "")

            # 调用LLM
            response = await provider.text_chat(
                prompt=prompt,
                contexts=[],
                personality=persona_name if persona_name else None
            )

            return response.completion_text if response else ""
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return ""

    @filter.command("jrrp")
    async def jrrp(self, event: AstrMessageEvent):
        """查看今日人品"""
        if not self.config.get("enable_plugin", True):
            return

        today = date.today().strftime("%Y-%m-%d")
        user_info = await self._get_user_info(event)
        user_id = user_info["user_id"]

        # 加载数据
        fortunes = await self._load_json("fortunes.json")
        if today not in fortunes:
            fortunes[today] = {}

        # 检查是否已测试
        if user_id in fortunes[today]:
            # 查询模式
            data = fortunes[today][user_id]
            fortune = data["value"]
            level, emoji = self._get_fortune_level(fortune)

            # 格式化查询模板
            query_text = self.config["query_template"].format(
                title=user_info["title"],
                card=user_info["card"],
                nickname=user_info["nickname"],
                jrrp=fortune,
                fortune=level,
                femoji=emoji
            )

            # 如果开启了显示缓存结果
            if self.config.get("show_cached_result", True) and "result" in data:
                query_text += f"\n\n-----以下为今日运势测算场景还原-----\n{data['result']}"

            yield event.plain_result(query_text)
            return

        # 首次测试，先发送检测消息
        detecting_msg = self.config["detecting_message"].format(**user_info)
        yield event.plain_result(detecting_msg)

        # 生成人品值
        min_val = self.config.get("min_fortune", 0)
        max_val = self.config.get("max_fortune", 100)
        fortune = random.randint(min_val, max_val)
        level, emoji = self._get_fortune_level(fortune)

        # 准备LLM调用的信息
        llm_info = user_info.copy()
        llm_info.update({
            "jrrp": str(fortune),
            "fortune": level,
            "femoji": emoji
        })

        # 调用LLM生成内容
        process = await self._call_llm(self.config["process_prompt"], llm_info)
        advice = await self._call_llm(self.config["advice_prompt"], llm_info)

        # 使用默认值
        if not process:
            process = "水晶球中浮现出神秘的光芒..."
        if not advice:
            advice = "今天会是美好的一天！"

        # 格式化结果
        result = self.config["random_template"].format(
            process=process,
            jrrp=fortune,
            fortune=level,
            advice=advice
        )

        # 保存数据
        fortunes[today][user_id] = {
            "value": fortune,
            "level": level,
            "emoji": emoji,
            "result": result,
            "time": datetime.now().strftime("%H:%M:%S"),
            "user_info": user_info
        }
        await self._save_json("fortunes.json", fortunes)

        # 保存历史
        history = await self._load_json("history.json")
        if user_id not in history:
            history[user_id] = []
        history[user_id].append({
            "date": today,
            "value": fortune,
            "level": level
        })
        # 只保留配置的历史天数
        history_days = self.config.get("history_days", 30)
        history[user_id] = history[user_id][-history_days:]
        await self._save_json("history.json", history)

        yield event.plain_result(result)

    @filter.command("jrrprank")
    async def jrrprank(self, event: AstrMessageEvent):
        """查看群聊人品排行"""
        if not self.config.get("enable_plugin", True):
            return

        if event.is_private_chat():
            yield event.plain_result("排行榜仅在群聊中可用")
            return

        today = date.today().strftime("%Y-%m-%d")
        fortunes = await self._load_json("fortunes.json")

        if today not in fortunes or not fortunes[today]:
            yield event.plain_result("今天还没有人测试人品哦~")
            return

        # 排序
        sorted_users = sorted(
            fortunes[today].items(),
            key=lambda x: x[1]["value"],
            reverse=True
        )

        # 构建排行
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        ranks = []

        for idx, (user_id, data) in enumerate(sorted_users[:10]):
            medal = medals[idx] if idx < len(medals) else f"{idx+1}."
            user_info = data.get("user_info", {})
            nickname = user_info.get("nickname", f"用户{user_id[-4:]}")

            rank_text = self.config["rank_template"].format(
                medal=medal,
                nickname=nickname,
                jrrp=data["value"],
                fortune=data["level"]
            )
            ranks.append(rank_text)

        # 格式化排行榜
        result = self.config["rank_list_template"].format(
            date=today,
            ranks="\n".join(ranks)
        )

        yield event.plain_result(result)

    @filter.command("jrrphistory", alias={"jrrphi"})
    async def jrrphistory(self, event: AstrMessageEvent):
        """查看人品历史"""
        if not self.config.get("enable_plugin", True):
            return

        # 获取目标用户
        target_id = event.get_sender_id()
        target_info = await self._get_user_info(event)

        # 检查是否@了其他人
        for comp in event.message_obj.message:
            if hasattr(comp, 'qq'):
                target_id = str(comp.qq)
                # 简单处理，使用ID作为昵称
                target_info = {"nickname": f"用户{target_id[-4:]}"}
                break

        history = await self._load_json("history.json")

        if target_id not in history or not history[target_id]:
            yield event.plain_result(f"{target_info['nickname']} 还没有人品测试记录")
            return

        user_history = history[target_id]

        # 计算统计信息
        values = [record["value"] for record in user_history]
        avg_val = sum(values) / len(values)
        max_val = max(values)
        min_val = min(values)

        # 构建历史记录
        records = []
        for record in user_history[-10:]:  # 只显示最近10条
            records.append(f"{record['date']}: {record['value']} ({record['level']})")

        # 格式化结果
        result = self.config["history_template"].format(
            nickname=target_info['nickname'],
            records="\n".join(records),
            avgjrrp=f"{avg_val:.1f}",
            maxjrrp=max_val,
            minjrrp=min_val
        )

        yield event.plain_result(result)

    @filter.command("jrrpdelete", alias={"jrrpdel"})
    async def jrrpdelete(self, event: AstrMessageEvent, confirm: str = ""):
        """删除个人数据"""
        if not self.config.get("enable_plugin", True):
            return

        if confirm != "--confirm":
            yield event.plain_result("⚠️ 确定要删除你的所有人品数据吗？\n使用 /jrrpdelete --confirm 确认删除")
            return

        user_id = event.get_sender_id()
        user_info = await self._get_user_info(event)

        # 删除数据
        deleted = False

        # 删除fortune数据
        fortunes = await self._load_json("fortunes.json")
        for date_key in list(fortunes.keys()):
            if user_id in fortunes[date_key]:
                del fortunes[date_key][user_id]
                deleted = True
        await self._save_json("fortunes.json", fortunes)

        # 删除历史数据
        history = await self._load_json("history.json")
        if user_id in history:
            del history[user_id]
            deleted = True
        await self._save_json("history.json", history)

        if deleted:
            yield event.plain_result(f"✅ 已删除 {user_info['nickname']} 的所有人品数据")
        else:
            yield event.plain_result(f"ℹ️ {user_info['nickname']} 没有人品数据记录")

    @filter.command("jrrpreset", alias={"jrrpre"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def jrrpreset(self, event: AstrMessageEvent, confirm: str = ""):
        """删除所有数据（仅管理员）"""
        if not self.config.get("enable_plugin", True):
            return

        if confirm != "--confirm":
            yield event.plain_result("⚠️ 警告：此操作将删除所有人品数据！\n使用 /jrrpreset --confirm 确认删除")
            return

        # 删除所有数据文件
        for filename in ["fortunes.json", "history.json"]:
            filepath = os.path.join(self.data_dir, filename)
            if os.path.exists(filepath):
                os.remove(filepath)

        yield event.plain_result("✅ 已删除所有人品数据")
        logger.info(f"管理员 {event.get_sender_id()} 重置了所有人品数据")

    async def terminate(self):
        """插件卸载时调用"""
        logger.info("今日人品插件已卸载")
