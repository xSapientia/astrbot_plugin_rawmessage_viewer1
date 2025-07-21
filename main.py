import json
import asyncio
from typing import Optional, Dict, Any
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.platform import AiocqhttpAdapter


@register(
    "astrbot_plugin_rawmessage_viewer",
    "xSapientia",
    "查看和增强aiocqhttp原生消息的插件",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_rawmessage_viewer"
)
class RawMessageViewer(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.enhanced_messages: Dict[str, Any] = {}
        logger.info("astrbot_plugin_rawmessage_viewer 插件已加载")

    @filter.command("rawmessage", alias={"rawmsg"})
    async def show_raw_message(self, event: AstrMessageEvent):
        """查看napcat通过aiocqhttp传递的原生消息"""
        if event.get_platform_name() != "aiocqhttp":
            yield event.plain_result("此功能仅支持 aiocqhttp 平台")
            return

        try:
            raw_msg = event.message_obj.raw_message
            formatted_msg = self._format_raw_message(raw_msg)

            # 使用文字转图片功能，让消息更美观
            if self.config.get("use_image_render", True):
                url = await self.text_to_image(formatted_msg)
                yield event.image_result(url)
            else:
                yield event.plain_result(formatted_msg)

        except Exception as e:
            logger.error(f"获取原生消息失败: {e}")
            yield event.plain_result(f"获取原生消息失败: {str(e)}")

    @filter.on_decorating_result()
    async def inject_raw_message(self, event: AstrMessageEvent):
        """在消息前插入增强的原生消息内容"""
        if not self.config.get("enable_message_injection", True):
            return

        if event.get_platform_name() != "aiocqhttp":
            return

        try:
            # 获取或创建增强消息
            message_id = event.message_obj.message_id
            if message_id in self.enhanced_messages:
                enhanced_msg = self.enhanced_messages[message_id]
            else:
                enhanced_msg = await self._enhance_raw_message(event)
                self.enhanced_messages[message_id] = enhanced_msg

            # 格式化增强消息
            tip_content = f"[aiocqhttp] RawMessage {enhanced_msg}"

            # 在消息链前插入tip内容
            result = event.get_result()
            from astrbot.api.message_components import Plain

            # 创建新的消息链，在开头插入tip
            new_chain = [
                Plain(f"<tip>\n{tip_content}\n</tip>\n")
            ]
            new_chain.extend(result.chain)
            result.chain = new_chain

            # 记录日志
            logger.info(f"已插入增强原生消息: {tip_content}")

            # 清理旧的缓存（保留最近100条）
            if len(self.enhanced_messages) > 100:
                keys = list(self.enhanced_messages.keys())
                for key in keys[:50]:
                    del self.enhanced_messages[key]

        except Exception as e:
            logger.error(f"注入原生消息失败: {e}")

    async def _enhance_raw_message(self, event: AstrMessageEvent) -> Dict[str, Any]:
        """增强原生消息，获取性别和群头衔信息"""
        try:
            raw_msg = event.message_obj.raw_message
            enhanced_msg = dict(raw_msg)

            # 确保是aiocqhttp消息
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot
                    sender = enhanced_msg.get("sender", {})
                    user_id = sender.get("user_id")

                    # 获取性别信息
                    sex = "unknown"
                    title = "unknown"

                    try:
                        # 尝试获取用户信息
                        if user_id:
                            user_info = await client.api.get_stranger_info(user_id=user_id)
                            sex = user_info.get("sex", "unknown")

                        # 如果是群消息，尝试获取群头衔
                        if enhanced_msg.get("message_type") == "group" and enhanced_msg.get("group_id"):
                            group_member_info = await client.api.get_group_member_info(
                                group_id=enhanced_msg["group_id"],
                                user_id=user_id
                            )
                            title = group_member_info.get("title", "") or "unknown"
                            # 如果通过群成员信息也能获取性别，优先使用
                            if group_member_info.get("sex"):
                                sex = group_member_info["sex"]

                    except Exception as e:
                        logger.warning(f"获取用户额外信息失败: {e}")

                    # 更新sender信息
                    sender["sex"] = sex
                    sender["title"] = title
                    enhanced_msg["sender"] = sender

            return enhanced_msg

        except Exception as e:
            logger.error(f"增强原生消息失败: {e}")
            return event.message_obj.raw_message

    def _format_raw_message(self, raw_msg: Any) -> str:
        """格式化原生消息为可读字符串"""
        try:
            if isinstance(raw_msg, dict):
                # 美化JSON输出
                return json.dumps(raw_msg, ensure_ascii=False, indent=2)
            else:
                return str(raw_msg)
        except:
            return str(raw_msg)

    async def terminate(self):
        """插件卸载时的清理工作"""
        self.enhanced_messages.clear()

        # 根据配置决定是否删除文件
        if self.config.get("delete_on_uninstall", False):
            import os
            import shutil

            # 删除插件数据目录
            plugin_data_dir = f"data/plugin_data/{self.metadata.name}"
            if os.path.exists(plugin_data_dir):
                shutil.rmtree(plugin_data_dir)
                logger.info(f"已删除插件数据目录: {plugin_data_dir}")

            # 删除配置文件
            config_file = f"data/config/{self.metadata.name}_config.json"
            if os.path.exists(config_file):
                os.remove(config_file)
                logger.info(f"已删除配置文件: {config_file}")

        logger.info("astrbot_plugin_rawmessage_viewer 插件已卸载")
