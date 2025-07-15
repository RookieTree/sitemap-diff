import logging
import asyncio
from .manager import RSSManager
from pathlib import Path
from urllib.parse import urlparse
from core.config import telegram_config
from telegram import Update, Bot
from telegram.ext import ContextTypes, CommandHandler, Application

rss_manager = RSSManager()


async def get_chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    获取当前聊天的ID，用于配置TELEGRAM_TARGET_CHAT环境变量
    """
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title or update.effective_chat.first_name or "私聊"
    
    message = (
        f"📍 聊天信息:\n"
        f"名称: {chat_title}\n"
        f"ID: `{chat_id}`\n\n"
        f"💡 将此ID设置为TELEGRAM_TARGET_CHAT环境变量值"
    )
    
    await update.message.reply_text(message, parse_mode='Markdown')
    logging.info(f"用户请求聊天ID: {chat_title} (ID: {chat_id})")


async def send_update_notification(
    bot: Bot,
    url: str,
    new_urls: list[str],
    dated_file: Path | None,
    target_chat: str = None,
) -> None:
    """
    发送Sitemap更新通知，包括文件（如果可用）和新增URL列表。
    """
    chat_id = target_chat or telegram_config["target_chat"]
    if not chat_id:
        logging.error("未配置发送目标，请检查TELEGRAM_TARGET_CHAT环境变量")
        return

    # 验证chat_id有效性
    try:
        chat_info = await bot.get_chat(chat_id)
        logging.info(f"目标聊天验证成功: {chat_info.title or chat_info.first_name} (ID: {chat_id})")
    except Exception as e:
        logging.error(f"无效的聊天ID {chat_id}: {str(e)}")
        logging.error("请检查以下可能的问题:")
        logging.error("1. TELEGRAM_TARGET_CHAT环境变量配置是否正确")
        logging.error("2. Bot是否已添加到目标群组/频道")
        logging.error("3. Bot是否具有发送消息权限")
        logging.error("4. 如果是私聊，用户是否已阻止Bot")
        return

    domain = urlparse(url).netloc

    try:
        if dated_file and dated_file.exists():
            # 根据是否有新增URL，分别构造美化后的标题
            if new_urls:
                header_message = (
                    f"✨ {domain} ✨\n"
                    f"------------------------------------\n"
                    f"发现新增内容！ (共 {len(new_urls)} 条)\n"
                    f"来源: {url}\n"
                )
            else:
                header_message = (
                    f"✅ {domain}\n"
                    f"------------------------------------\n"
                    f"{domain} 今日sitemap无更新\n"
                    f"来源: {url}\n"
                    f"------------------------------------"
                )
        try:
            await bot.send_document(
                chat_id=chat_id,
                document=dated_file,
                caption=header_message,
                read_timeout=30,
                write_timeout=30,
                connect_timeout=30,
            )
            logging.info(f"已发送sitemap文件: {dated_file} for {url}")
        except Exception as e:
            logging.error(f"发送文档失败: {str(e)}, 改为发送文本消息")
            # 文档发送失败时，改为发送文本消息
            await bot.send_message(
                chat_id=chat_id, 
                text=header_message, 
                disable_web_page_preview=True
            )
            await asyncio.sleep(5)
        
        # 无论发送成功或失败，都尝试删除临时文件
        try:
            dated_file.unlink()
            logging.info(f"已删除临时sitemap文件: {dated_file}")
        except OSError as e:
            logging.error(f"删除文件失败: {dated_file}, Error: {str(e)}")
        else:
            # 没有文件时，发送美化标题文本
            if not new_urls:
                message = f"✅ {domain} 今日没有更新"
                await bot.send_message(
                    chat_id=chat_id, text=message, disable_web_page_preview=True
                )
                await asyncio.sleep(5)
            else:
                header_message = (
                    f"✨ {domain} ✨\n"
                    f"------------------------------------\n"
                    f"发现新增内容！ (共 {len(new_urls)} 条)\n"
                    f"来源: {url}\n"
                )
                await bot.send_message(
                    chat_id=chat_id, text=header_message, disable_web_page_preview=True
                )
                await asyncio.sleep(5)

        await asyncio.sleep(5)
        if new_urls:
            logging.info(f"开始发送 {len(new_urls)} 个新URL for {domain}")
            for u in new_urls:
                await bot.send_message(
                    chat_id=chat_id, text=u, disable_web_page_preview=False
                )
                logging.info(f"已发送URL: {u}")
                await asyncio.sleep(5)
            logging.info(f"已发送 {len(new_urls)} 个新URL for {domain}")

            # 发送更新结束的消息
            await asyncio.sleep(5)
            end_message = (
                f"✨ {domain} 更新推送完成 ✨\n------------------------------------"
            )
            await bot.send_message(
                chat_id=chat_id, text=end_message, disable_web_page_preview=True
            )
            logging.info(f"已发送更新结束消息 for {domain}")
    except Exception as e:
        error_msg = str(e)
        if "Chat not found" in error_msg:
            logging.error(f"聊天未找到错误 for {url}: {error_msg}")
            logging.error("可能的解决方案:")
            logging.error("1. 检查TELEGRAM_TARGET_CHAT环境变量是否配置正确")
            logging.error("2. 确保Bot已添加到目标群组并具有发送消息权限")
            logging.error("3. 如果是私聊，确保用户没有阻止Bot")
        elif "Forbidden" in error_msg:
            logging.error(f"权限被拒绝 for {url}: {error_msg}")
            logging.error("Bot可能被踢出群组或权限不足，请重新添加Bot并授予适当权限")
        elif "Bad Request" in error_msg:
            logging.error(f"请求格式错误 for {url}: {error_msg}")
            logging.error("请检查发送的内容格式是否正确")
        else:
            logging.error(f"发送URL更新消息失败 for {url}: {error_msg}", exc_info=True)
        # logging.traceback.print_exc()


async def rss_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /rss 命令"""
    user = update.message.from_user
    chat_id = update.message.chat_id
    logging.info(f"收到RSS命令 - 用户: {user.username}(ID:{user.id}) 聊天ID: {chat_id}")

    if not context.args:
        logging.info("显示RSS命令帮助信息")
        await update.message.reply_text(
            "请使用以下命令：\n"
            "/rss list - 显示所有监控的sitemap\n"
            "/rss add URL - 添加sitemap监控（URL必须以sitemap.xml结尾）\n"
            "/rss del URL - 删除sitemap监控"
        )
        return

    cmd = context.args[0].lower()
    if cmd == "list":
        logging.info("执行list命令")
        feeds = rss_manager.get_feeds()
        if not feeds:
            logging.info("RSS订阅列表为空")
            await update.message.reply_text("当前没有RSS订阅")
            return

        feed_list = "\n".join([f"- {feed}" for feed in feeds])
        logging.info(f"显示RSS订阅列表，共 {len(feeds)} 个")
        await update.message.reply_text(f"当前RSS订阅列表：\n{feed_list}")

    elif cmd == "add":
        if len(context.args) < 2:
            logging.warning("add命令缺少URL参数")
            await update.message.reply_text(
                "请提供sitemap.xml的URL\n例如：/rss add https://example.com/sitemap.xml"
            )
            return

        url = context.args[1]
        # 检查URL是否包含sitemap关键词，不再强制要求.xml后缀
        if "sitemap" not in url.lower():
            logging.warning(f"无效的sitemap URL: {url} (URL需包含sitemap关键词)")
            await update.message.reply_text("URL必须以sitemap.xml结尾")
            return

        logging.info(f"执行add命令，URL: {url}")
        success, error_msg, dated_file, new_urls = rss_manager.add_feed(url)

        if success:
            if "已存在的feed更新成功" in error_msg:
                await update.message.reply_text(f"该sitemap已在监控列表中")
            else:
                await update.message.reply_text(f"成功添加sitemap监控：{url}")

            # 调用新的合并函数
            await send_update_notification(context.bot, url, new_urls, dated_file)
            logging.info(f"已尝试发送更新通知 for {url} after add command")

        else:
            if "今天已经更新过此sitemap" in error_msg:
                # 获取当前文件并发送给用户 (这部分是发送给命令发起者的，逻辑保持)
                try:
                    domain = urlparse(url).netloc
                    current_file = (
                        rss_manager.sitemap_dir / domain / "sitemap-current.xml"
                    )
                    if current_file.exists():
                        await context.bot.send_document(
                            chat_id=update.effective_chat.id,  # 发送给命令发起者
                            document=current_file,
                            caption=f"今天的Sitemap文件\nURL: {url}",
                        )
                        await update.message.reply_text(f"该sitemap今天已经更新过")
                        # 即使今天更新过，也尝试给频道发送一次通知（可能包含上次比较的结果）
                        # 注意：这里 dated_file 可能不存在，需要处理
                        _, _, dated_file_maybe, existing_new_urls = (
                            rss_manager.download_sitemap(url)
                        )  # 再次调用以获取文件和URL
                        if dated_file_maybe:
                            await send_update_notification(
                                context.bot, url, existing_new_urls, dated_file_maybe
                            )

                    else:
                        await update.message.reply_text(f"该sitemap今天已经更新过")
                except Exception as e:
                    logging.error(f"发送文件给用户失败: {str(e)}")
                    await update.message.reply_text(f"该sitemap今天已经更新过")
            else:
                logging.error(f"添加sitemap监控失败: {url} 原因: {error_msg}")
                await update.message.reply_text(
                    f"添加sitemap监控失败：{url}\n原因：{error_msg}"
                )

    elif cmd == "del":
        if len(context.args) < 2:
            logging.warning("del命令缺少URL参数")
            await update.message.reply_text(
                "请提供要删除的RSS订阅链接\n例如：/rss del https://example.com/feed.xml"
            )
            return

        url = context.args[1]
        logging.info(f"执行del命令，URL: {url}")
        success, error_msg = rss_manager.remove_feed(url)
        if success:
            logging.info(f"成功删除RSS订阅: {url}")
            await update.message.reply_text(f"成功删除RSS订阅：{url}")
        else:
            logging.error(f"删除RSS订阅失败: {url} 原因: {error_msg}")
            await update.message.reply_text(
                f"删除RSS订阅失败：{url}\n原因：{error_msg}"
            )


def register_commands(application: Application):
    """注册RSS相关的命令"""
    application.add_handler(CommandHandler("rss", rss_command))
    application.add_handler(CommandHandler("news", force_summary_command_handler))
    application.add_handler(CommandHandler("chatid", get_chat_id_command))


async def force_send_keywords_summary(bot: Bot, target_chat: str = None) -> None:
    """
    强制从存储的 current 和 latest sitemap 文件比对生成并发送关键词汇总。
    """
    chat_id = target_chat or telegram_config["target_chat"]
    if not chat_id:
        logging.error("未配置发送目标，请检查TELEGRAM_TARGET_CHAT环境变量")
        return

    all_new_urls_for_summary = []
    feeds = rss_manager.get_feeds()

    if not feeds:
        logging.info("没有配置任何 sitemap feeds，无法生成汇总。")
        try:
            await bot.send_message(chat_id=chat_id, text="⚠️ 没有配置任何 sitemap feeds，无法生成关键词汇总。")
        except Exception as e:
            logging.error(f"发送无 feeds 通知失败: {str(e)}")
        return

    logging.info(f"开始为 {len(feeds)} 个 feeds 强制生成关键词汇总。")
    for feed_url in feeds:
        try:
            domain = urlparse(feed_url).netloc
            domain_dir = rss_manager.sitemap_dir / domain
            current_sitemap_file = domain_dir / "sitemap-current.xml"
            # 'latest_sitemap_file' actually stores the sitemap content from the run *before* 'current_sitemap_file' was updated.
            # So it's the 'old' or 'previous' sitemap.
            latest_sitemap_file = domain_dir / "sitemap-latest.xml"

            if current_sitemap_file.exists() and latest_sitemap_file.exists():
                current_content = current_sitemap_file.read_text()
                latest_content = latest_sitemap_file.read_text() # This is the 'old' content

                # rss_manager.compare_sitemaps expects (new_content, old_content)
                new_urls_for_feed = rss_manager.compare_sitemaps(current_content, latest_content)
                if new_urls_for_feed:
                    logging.info(f"强制汇总 - 为 {domain} 从 current/latest 文件比较中发现 {len(new_urls_for_feed)} 个新 URL。")
                    all_new_urls_for_summary.extend(new_urls_for_feed)
                else:
                    logging.info(f"强制汇总 - 为 {domain} 从 current/latest 文件比较中未发现新 URL。")
            else:
                logging.warning(f"强制汇总 - 对于 {feed_url}，current ({current_sitemap_file.exists()}) 或 latest ({latest_sitemap_file.exists()}) sitemap 文件不存在，跳过比较。")
        except Exception as e:
            logging.error(f"强制汇总 - 处理 feed {feed_url} 时出错: {str(e)}")
            continue

    if all_new_urls_for_summary:
        logging.info(f"强制汇总 - 共收集到 {len(all_new_urls_for_summary)} 个新 URL 用于生成汇总。")
        await send_keywords_summary(bot, all_new_urls_for_summary, target_chat=chat_id)
    else:
        logging.info("强制汇总 - 所有 feeds 均未从 current/latest 文件比较中发现新 URL，不发送汇总。")
        try:
            await bot.send_message(chat_id=chat_id, text="ℹ️ 所有监控源的 current/latest sitemap 对比均无新增内容，无需发送关键词汇总。")
        except Exception as e:
            logging.error(f"发送无新增内容通知失败: {str(e)}")


async def force_summary_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /news 命令，强制发送关键词汇总"""
    user = update.message.from_user
    chat_id = update.message.chat_id # Chat where the command was issued
    logging.info(f"收到 /news 命令 - 用户: {user.username}(ID:{user.id}) 聊天ID: {chat_id}")

    try:
        await update.message.reply_text("⏳ 正在尝试从已存储的 sitemap 数据生成并发送关键词汇总...")

        # The actual summary is sent to telegram_config["target_chat"]
        await force_send_keywords_summary(context.bot)

        logging.info(f"已通过 /news 命令尝试强制发送关键词汇总。")
        await update.message.reply_text("✅ 关键词汇总已尝试发送至目标频道。如果没有任何新增内容，则不会发送。")
    except Exception as e:
        logging.error(f"执行 /news 命令失败: {str(e)}", exc_info=True)
        try:
            await update.message.reply_text(f"❌ 执行 /news 命令时出错: {str(e)}")
        except Exception as e_reply:
            logging.error(f"发送 /news 错误回执失败: {str(e_reply)}")


async def send_keywords_summary(
    bot: Bot,
    all_new_urls: list[str],
    target_chat: str = None,
) -> None:
    """
    从URL列表中提取关键词并按域名分组发送汇总消息

    Args:
        bot: Telegram Bot实例
        all_new_urls: 所有新增URL的列表
        target_chat: 发送目标ID,默认使用配置中的target_chat
    """
    chat_id = target_chat or telegram_config["target_chat"]
    if not chat_id:
        logging.error("未配置发送目标，请检查TELEGRAM_TARGET_CHAT环境变量")
        return

    if not all_new_urls:
        return

    # 创建域名-关键词映射字典
    domain_keywords = {}

    # 从URL中提取域名和关键词
    for url in all_new_urls:
        try:
            # 解析URL获取域名和路径
            parsed_url = urlparse(url)
            domain = parsed_url.netloc

            # 提取路径最后部分作为关键词
            path_parts = parsed_url.path.rstrip("/").split("/")
            if path_parts and path_parts[-1]:  # 确保有路径且最后部分不为空
                keyword = path_parts[-1]
                if keyword.strip():
                    # 将关键词添加到对应域名的列表中
                    if domain not in domain_keywords:
                        domain_keywords[domain] = []
                    domain_keywords[domain].append(keyword)
        except Exception as e:
            logging.debug(f"从URL提取关键词失败: {url}, 错误: {str(e)}")
            continue

    # 对每个域名的关键词列表去重
    for domain in domain_keywords:
        domain_keywords[domain] = list(set(domain_keywords[domain]))

    # 如果有关键词，构建并发送消息
    if domain_keywords:
        # 构建今日新增关键词消息，按域名分组
        summary_message = (
            "━━━━━━━━━━━━━━━━━━\n" "🎯 #今日新增 #关键词 #速览 🎯\n" "━━━━━━━━━━━━━━━━━━\n\n"
        )

        # 按域名分组展示关键词
        for domain, keywords in domain_keywords.items():
            if keywords:  # 确保该域名有关键词
                summary_message += f"📌 {domain}:\n"
                for i, keyword in enumerate(keywords, 1):
                    summary_message += f"  {i}. {keyword}\n"
                summary_message += "\n"  # 域名之间添加空行分隔

        # 发送汇总消息
        try:
            await bot.send_message(
                chat_id=chat_id, text=summary_message, disable_web_page_preview=True
            )
        except Exception as e:
            logging.error(f"发送关键词汇总消息失败 (chat_id: {chat_id}): {str(e)}")
