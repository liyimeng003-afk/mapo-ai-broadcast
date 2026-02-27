from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import unescape
import re
import logging
import os

app = Flask(__name__, static_folder='.')
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RSS 数据源配置
RSS_SOURCES = [
    {
        'name': '机器之心',
        'url': 'https://www.jiqizhixin.com/rss',
        'category': 'AI 前沿',
        'color': 'style="background-color: #8B7355; color: #FAF8F3;"',
        'filter_keywords': False
    },
    {
        'name': '36氪',
        'url': 'https://36kr.com/feed',
        'category': 'AI 创业',
        'color': 'style="background-color: #6B5444; color: #FAF8F3;"',
        'filter_keywords': True
    },
    {
        'name': '晚点LatePost',
        'url': 'https://www.latepost.com/feed',
        'category': '深度报道',
        'color': 'style="background-color: #9CA3AF; color: #FAF8F3;"',
        'filter_keywords': True
    },
    {
        'name': 'TechCrunch',
        'url': 'https://techcrunch.com/feed/',
        'category': 'Global Tech',
        'color': 'style="background-color: #D4C5A9; color: #4A3F35;"',
        'filter_keywords': True
    },
    {
        'name': 'MIT Technology Review',
        'url': 'https://www.technologyreview.com/feed/',
        'category': 'AI Research',
        'color': 'style="background-color: #8B7355; color: #FAF8F3;"',
        'filter_keywords': True
    },
    {
        'name': 'The Verge',
        'url': 'https://www.theverge.com/rss/index.xml',
        'category': 'Tech News',
        'color': 'style="background-color: #4A3F35; color: #FAF8F3;"',
        'filter_keywords': True
    }
]

AI_KEYWORDS = [
    'ai', 'artificial intelligence', 'machine learning', 'deep learning',
    'neural network', 'chatgpt', 'gpt', 'llm', 'openai', 'anthropic',
    'claude', 'gemini', 'copilot', 'automation', 'robot', 'computer vision',
    '人工智能', '机器学习', '深度学习', '神经网络', '大模型', '智能',
    'generative ai', 'gen ai', 'transformer', 'nlp', 'natural language',
    '算法', '科技', 'tech', 'technology', 'startup', '创业', '智能化'
]

def strip_html(text):
    """移除 HTML 标签"""
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    return text.strip()

def contains_ai_keywords(text):
    """检查文本是否包含 AI 关键词"""
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in AI_KEYWORDS)

def parse_date(date_str):
    """解析日期字符串"""
    if not date_str:
        return datetime.now()

    # 尝试多种日期格式
    formats = [
        '%a, %d %b %Y %H:%M:%S %z',  # RFC 822
        '%a, %d %b %Y %H:%M:%S %Z',
        '%Y-%m-%dT%H:%M:%S%z',       # ISO 8601
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d %H:%M:%S',
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except:
            continue

    return datetime.now()

def fetch_rss(source, max_retries=3):
    """获取并解析 RSS 源，带重试机制"""
    news_list = []

    for attempt in range(max_retries):
        try:
            logger.info(f"正在获取 {source['name']} (尝试 {attempt + 1}/{max_retries})...")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            # 增加超时时间到20秒
            response = requests.get(source['url'], headers=headers, timeout=20)
            response.raise_for_status()

            # 解析 XML
            root = ET.fromstring(response.content)

            # 查找所有 item 元素
            items = root.findall('.//item')

            if not items:
                logger.warning(f"{source['name']}: 未找到任何新闻条目")
                continue

            # 改为72小时（3天）
            seventy_two_hours_ago = datetime.now() - timedelta(hours=72)

        for item in items:
            try:
                title = item.find('title')
                title = title.text if title is not None else ''

                link = item.find('link')
                link = link.text if link is not None else ''

                description = item.find('description')
                description = description.text if description is not None else ''
                description = strip_html(description)

                pub_date = item.find('pubDate')
                pub_date_str = pub_date.text if pub_date is not None else ''
                pub_date_obj = parse_date(pub_date_str)

                # 移除时区信息以便比较
                if pub_date_obj.tzinfo:
                    pub_date_obj = pub_date_obj.replace(tzinfo=None)

                # 过滤 72 小时以前的新闻
                if pub_date_obj < seventy_two_hours_ago:
                    continue

                # 如果需要关键词筛选
                if source['filter_keywords']:
                    if not contains_ai_keywords(title + ' ' + description):
                        continue

                news_item = {
                    'title': title,
                    'link': link,
                    'description': description[:200],
                    'pubDate': pub_date_obj.isoformat(),
                    'timestamp': int(pub_date_obj.timestamp() * 1000),
                    'source': source['name'],
                    'category': source['category'],
                    'color': source['color']
                }

                news_list.append(news_item)

            except Exception as e:
                logger.warning(f"解析条目失败: {e}")
                continue

            logger.info(f"✅ {source['name']}: 成功获取 {len(news_list)} 条（72小时内）")
            return news_list  # 成功获取后直接返回，不再重试

        except Exception as e:
            logger.error(f"❌ {source['name']} 第 {attempt + 1} 次尝试失败: {e}")
            if attempt < max_retries - 1:
                logger.info(f"等待 2 秒后重试...")
                import time
                time.sleep(2)
            continue

    # 所有重试都失败
    logger.error(f"❌ {source['name']} 在 {max_retries} 次尝试后仍然失败")
    return news_list

@app.route('/')
def index():
    """返回前端页面"""
    return send_from_directory('.', 'index.html')

@app.route('/api/news', methods=['GET'])
def get_news():
    """获取所有新闻源的新闻"""
    all_news = []

    for source in RSS_SOURCES:
        news = fetch_rss(source)
        all_news.extend(news)

    # 按时间倒序排序
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)

    logger.info(f"总共返回 {len(all_news)} 条新闻")

    return jsonify({
        'status': 'ok',
        'count': len(all_news),
        'news': all_news
    })

@app.route('/api/sources', methods=['GET'])
def get_sources():
    """获取所有新闻源列表"""
    sources = [{'name': s['name'], 'category': s['category']} for s in RSS_SOURCES]
    return jsonify({
        'status': 'ok',
        'sources': sources
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'message': 'AI 新闻聚合 API 正在运行'
    })

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))

    print("=" * 50)
    print("🚀 马坡村头大喇叭 AI 新闻版 - API 启动中...")
    print("=" * 50)
    print(f"📡 API 地址: http://0.0.0.0:{port}")
    print(f"🔍 获取新闻: http://0.0.0.0:{port}/api/news")
    print(f"📋 新闻源列表: http://0.0.0.0:{port}/api/sources")
    print("=" * 50)

    app.run(host='0.0.0.0', port=port, debug=False)
