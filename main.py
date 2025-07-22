import json
import asyncio
from typing import Optional, Dict, Any, List
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig


@register(
    "astrbot_plugin_rawmessage_viewer1",
    "xSapientia",
    "查看和增强aiocqhttp原生消息的插件",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_rawmessage_viewer1"
)
class RawMessageViewer(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.enhanced_messages: Dict[str, Any] = {}
        self.processed_messages = set()  # 防止重复处理
        self.tip_contents: Dict[str, str] = {}  # 存储tip内容
        logger.info("astrbot_plugin_rawmessage_viewer1 插件已加载")

    @filter.command("rawmessage", alias={"rawmsg"})
    async def show_raw_message(self, event: AstrMessageEvent):
        """查看napcat通过aiocqhttp传递的原生消息"""
        if event.get_platform_name() != "aiocqhttp":
            yield event.plain_result("此功能仅支持 aiocqhttp 平台")
            return

        try:
            # 获取增强后的消息
            message_id = event.message_obj.message_id

            # 先检查是否有已保存的tip内容
            if message_id in self.tip_contents:
                tip_content = self.tip_contents[message_id]
            elif message_id in self.enhanced_messages:
                enhanced_msg = self.enhanced_messages[message_id]
                tip_content = f"[aiocqhttp] RawMessage {enhanced_msg}"
            else:
                # 如果都没有，重新生成
                enhanced_msg = await self._enhance_raw_message(event)
                self.enhanced_messages[message_id] = enhanced_msg
                tip_content = f"[aiocqhttp] RawMessage {enhanced_msg}"

            # 格式化输出
            formatted_output = f"<tip>\n{tip_content}\n</tip>"

            # 使用文字转图片功能，让消息更美观
            if self.config.get("use_image_render", True):
                url = await self.text_to_image(formatted_output)
                yield event.image_result(url)
            else:
                yield event.plain_result(formatted_output)

        except Exception as e:
            logger.error(f"获取原生消息失败: {e}")
            yield event.plain_result(f"获取原生消息失败: {str(e)}")

    @filter.event_message_type(filter.EventMessageType.ALL, priority=100)  # 设置高优先级
    async def process_incoming_message(self, event: AstrMessageEvent):
        """处理所有传入的消息，在消息到达其他处理器之前"""
        if not self.config.get("enable_message_injection", True):
            return

        if event.get_platform_name() != "aiocqhttp":
            return

        # 防止重复处理
        message_id = event.message_obj.message_id
        if message_id in self.processed_messages:
            return
        self.processed_messages.add(message_id)

        try:
            # 获取或创建增强消息
            if message_id not in self.enhanced_messages:
                enhanced_msg = await self._enhance_raw_message(event)
                self.enhanced_messages[message_id] = enhanced_msg
            else:
                enhanced_msg = self.enhanced_messages[message_id]

            # 格式化增强消息为tip内容
            tip_content = f"[aiocqhttp] RawMessage {enhanced_msg}"

            # 保存tip内容供后续查看
            self.tip_contents[message_id] = tip_content

            # 保存原始消息内容的副本
            original_message_str = event.message_obj.message_str
            original_message_chain = list(event.message_obj.message)  # 创建副本

            # 创建tip组件
            from astrbot.api.message_components import Plain
            tip_component = Plain(f"<tip>\n{tip_content}\n</tip>\n")

            # 创建新的消息链（不修改原始消息链）
            new_message_chain = [tip_component] + original_message_chain

            # 更新消息对象，但保持其他属性不变
            event.message_obj.message = new_message_chain
            event.message_obj.message_str = f"<tip>\n{tip_content}\n</tip>\n{original_message_str}"

            # 记录日志 - 显示AstrBot最终接收到的内容
            logger.info(f"[RawMessageViewer] 成功在消息前插入增强内容")
            logger.info(f"[RawMessageViewer] 原始消息: {original_message_str}")
            logger.info(f"[RawMessageViewer] AstrBot最终接收到的消息: {event.message_obj.message_str}")

            # 清理旧的缓存
            cache_size = self.config.get("advanced_settings", {}).get("cache_size", 100)
            if len(self.enhanced_messages) > cache_size:
                keys = list(self.enhanced_messages.keys())
                for key in keys[:len(keys)//2]:
                    del self.enhanced_messages[key]
                    self.processed_messages.discard(key)
                    self.tip_contents.pop(key, None)

        except Exception as e:
            logger.error(f"处理传入消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _enhance_raw_message(self, event: AstrMessageEvent) -> Dict[str, Any]:
        """增强原生消息，获取性别和群头衔信息，以及@对象信息"""
        try:
            # 创建原生消息的深拷贝，避免修改原始数据
            import copy

            # 获取原始的raw_message
            if hasattr(event.message_obj, 'raw_message') and isinstance(event.message_obj.raw_message, dict):
                raw_msg = copy.deepcopy(event.message_obj.raw_message)
            else:
                # 如果raw_message不可用，返回一个基本结构
                raw_msg = {
                    "message_type": "unknown",
                    "sender": {"user_id": 0, "nickname": "unknown"},
                    "message": event.message_obj.message_str
                }

            # 确保是aiocqhttp消息
            if event.get_platform_name() == "aiocqhttp":
                client = await self._get_aiocqhttp_client(event)

                if client:
                    # 增强发送者信息
                    sender = raw_msg.get("sender", {})
                    user_id = sender.get("user_id")

                    # 初始化默认值
                    sex = "unknown"
                    title = "unknown"

                    try:
                        # 尝试获取用户信息
                        if user_id and hasattr(client, 'api'):
                            try:
                                user_info = await client.api.get_stranger_info(user_id=user_id)
                                sex = user_info.get("sex", "unknown")
                            except:
                                pass

                            # 如果是群消息，尝试获取群头衔
                            if raw_msg.get("message_type") == "group" and raw_msg.get("group_id"):
                                try:
                                    group_member_info = await client.api.get_group_member_info(
                                        group_id=raw_msg["group_id"],
                                        user_id=user_id
                                    )
                                    title = group_member_info.get("title", "") or "unknown"
                                    # 如果通过群成员信息也能获取性别，优先使用
                                    if group_member_info.get("sex"):
                                        sex = group_member_info["sex"]
                                except:
                                    pass

                    except Exception as e:
                        logger.warning(f"获取用户额外信息失败: {e}")

                    # 更新sender信息
                    sender["sex"] = sex
                    sender["title"] = title
                    raw_msg["sender"] = sender

                    # 处理@信息
                    ater_info_list = await self._get_at_info_list(event, client, raw_msg)
                    # 添加多个ater结构体
                    for idx, ater_info in enumerate(ater_info_list, 1):
                        raw_msg[f"ater{idx}"] = ater_info

                else:
                    logger.warning("无法获取aiocqhttp客户端，跳过信息增强")
                    # 添加默认值
                    sender = raw_msg.get("sender", {})
                    sender["sex"] = "unknown"
                    sender["title"] = "unknown"
                    raw_msg["sender"] = sender

            return raw_msg

        except Exception as e:
            logger.error(f"增强原生消息失败: {e}")
            # 返回一个基本的结构，避免崩溃
            return {
                "message_type": "unknown",
                "sender": {"user_id": 0, "nickname": "unknown", "sex": "unknown", "title": "unknown"},
                "message": event.message_obj.message_str
            }

    async def _get_at_info_list(self, event: AstrMessageEvent, client: Any, raw_msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取消息中所有@对象的信息"""
        ater_info_list = []

        try:
            # 检查消息链中是否有At类型的消息
            message_chain = event.message_obj.message
            at_users = []

            # 从消息链中提取所有@的用户
            from astrbot.api.message_components import At
            for msg_comp in message_chain:
                if isinstance(msg_comp, At):
                    at_users.append(msg_comp.qq)

            # 获取所有@用户的信息
            for at_user_id in at_users:
                ater_info = {
                    "user_id": at_user_id,
                    "nickname": "unknown",
                    "card": "unknown",
                    "role": "unknown",
                    "sex": "unknown",
                    "title": "unknown"
                }

                try:
                    # 获取用户基本信息
                    user_info = await client.api.get_stranger_info(user_id=at_user_id)
                    ater_info["nickname"] = user_info.get("nickname", "unknown")
                    ater_info["sex"] = user_info.get("sex", "unknown")

                    # 如果是群消息，获取群相关信息
                    if raw_msg.get("message_type") == "group" and raw_msg.get("group_id"):
                        try:
                            group_member_info = await client.api.get_group_member_info(
                                group_id=raw_msg["group_id"],
                                user_id=at_user_id
                            )
                            ater_info["card"] = group_member_info.get("card", "") or ater_info["nickname"]
                            ater_info["role"] = group_member_info.get("role", "unknown")
                            ater_info["title"] = group_member_info.get("title", "") or "unknown"
                            # 群成员信息中的性别可能更准确
                            if group_member_info.get("sex"):
                                ater_info["sex"] = group_member_info["sex"]
                        except Exception as e:
                            logger.warning(f"获取@用户 {at_user_id} 群信息失败: {e}")

                except Exception as e:
                    logger.warning(f"获取@用户 {at_user_id} 信息失败: {e}")

                ater_info_list.append(ater_info)

        except Exception as e:
            logger.error(f"处理@信息失败: {e}")

        return ater_info_list

    async def _get_aiocqhttp_client(self, event: AstrMessageEvent) -> Optional[Any]:
        """获取aiocqhttp客户端"""
        client = None

        try:
            # 方法1：从context获取platform_manager
            if hasattr(self.context, 'platform_manager'):
                platforms = self.context.platform_manager.get_insts()
                for platform in platforms:
                    if hasattr(platform, 'metadata') and platform.metadata.name == 'aiocqhttp':
                        if hasattr(platform, 'client'):
                            client = platform.client
                            break

            # 方法2：尝试从event获取
            if not client and hasattr(event, 'bot'):
                client = event.bot

            # 方法3：尝试从message_obj获取
            if not client and hasattr(event, 'message_obj'):
                if hasattr(event.message_obj, 'platform'):
                    platform = event.message_obj.platform
                    if hasattr(platform, 'client'):
                        client = platform.client

        except Exception as e:
            logger.error(f"获取aiocqhttp客户端时出错: {e}")

        return client

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
        self.processed_messages.clear()
        self.tip_contents.clear()

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

        logger.info("astrbot_plugin_rawmessage_viewer1 插件已卸载")
