#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Naver Cafe Author Crawler
특정 작가의 모든 게시물을 자동으로 수집하는 크롤러
"""

import os
import sys
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
from abc import ABC, abstractmethod

try:
    import requests
    from bs4 import BeautifulSoup
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError as e:
    print(f"Error: Required package not found - {e}")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)


class Logger:
    """Simple logging utility"""
    def __init__(self, name: str):
        self.name = name
        self.logs: List[Dict] = []

    def log(self, message: str, level: str = 'INFO'):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = {
            'timestamp': timestamp,
            'level': level,
            'message': message
        }
        self.logs.append(log_entry)
        prefix = f"[{timestamp}] [{level}]"
        print(f"{prefix} {message}")

    def info(self, message: str):
        self.log(message, 'INFO')

    def success(self, message: str):
        self.log(message, 'SUCCESS')

    def warning(self, message: str):
        self.log(message, 'WARNING')

    def error(self, message: str):
        self.log(message, 'ERROR')

    def export_logs(self, filepath: str):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.logs, f, ensure_ascii=False, indent=2)


class NaverAuthenticator:
    """Handle Naver authentication"""
    def __init__(self, user_id: str, password: str, logger: Logger):
        self.user_id = user_id
        self.password = password
        self.logger = logger
        self.driver = None
        self.session = requests.Session()

    def setup_driver(self) -> webdriver.Chrome:
        """Setup Selenium WebDriver"""
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--start-maximized')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=options)
            self.logger.info("WebDriver initialized")
            return self.driver
        except Exception as e:
            self.logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def login(self) -> bool:
        """Login to Naver"""
        try:
            self.logger.info("Starting Naver login process...")
            self.driver.get("https://nid.naver.com/nidlogin.login")
            
            # Wait for login form
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "id"))
            )
            
            # Input credentials
            self.driver.find_element(By.ID, "id").send_keys(self.user_id)
            self.driver.find_element(By.ID, "pw").send_keys(self.password)
            self.driver.find_element(By.ID, "log.login").click()
            
            # Wait for redirect
            time.sleep(3)
            
            # Check if login was successful
            if "naver.com" in self.driver.current_url and "login" not in self.driver.current_url:
                self.logger.success("Successfully logged in to Naver")
                return True
            else:
                self.logger.error("Login failed - check credentials")
                return False
                
        except Exception as e:
            self.logger.error(f"Login error: {e}")
            return False

    def get_cookies(self) -> Dict:
        """Extract cookies from Selenium driver"""
        cookies = {}
        for cookie in self.driver.get_cookies():
            cookies[cookie['name']] = cookie['value']
        return cookies

    def close(self):
        """Close WebDriver"""
        if self.driver:
            self.driver.quit()


class ArticleParser:
    """Parse article content"""
    def __init__(self, logger: Logger):
        self.logger = logger

    def parse_article(self, html: str, article_url: str) -> Dict:
        """Parse article from HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            article = {
                'url': article_url,
                'title': self._extract_title(soup),
                'author': self._extract_author(soup),
                'date': self._extract_date(soup),
                'content': self._extract_content(soup),
                'images': self._extract_images(soup),
                'views': self._extract_views(soup),
                'comments': []
            }
            
            return article
        except Exception as e:
            self.logger.error(f"Error parsing article: {e}")
            return None

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title"""
        try:
            title = soup.find('h3', class_='article-title')
            return title.get_text(strip=True) if title else "Unknown"
        except:
            return "Unknown"

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract author name"""
        try:
            author = soup.find('span', class_='nickname')
            return author.get_text(strip=True) if author else "Anonymous"
        except:
            return "Anonymous"

    def _extract_date(self, soup: BeautifulSoup) -> str:
        """Extract publication date"""
        try:
            date = soup.find('span', class_='date')
            return date.get_text(strip=True) if date else "Unknown"
        except:
            return "Unknown"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract article content"""
        try:
            content = soup.find('div', class_='article-content')
            return content.get_text() if content else ""
        except:
            return ""

    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        """Extract image URLs"""
        try:
            images = []
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if src and 'http' in src:
                    images.append(src)
            return images
        except:
            return []

    def _extract_views(self, soup: BeautifulSoup) -> int:
        """Extract view count"""
        try:
            views = soup.find('span', class_='view-count')
            if views:
                count_str = views.get_text(strip=True).replace(',', '')
                return int(count_str)
        except:
            pass
        return 0


class MarkdownExporter:
    """Export data to Markdown format"""
    def __init__(self, logger: Logger):
        self.logger = logger

    def export_articles(self, articles: List[Dict], output_dir: str, author_name: str = "Author"):
        """Export articles to markdown files"""
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Create index file
            index_path = output_path / "INDEX.md"
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(f"# {author_name} Articles\n\n")
                f.write(f"**Total Articles:** {len(articles)}\n\n")
                f.write("## Article List\n\n")
                
                for i, article in enumerate(articles, 1):
                    filename = self._sanitize_filename(article['title'])
                    f.write(f"{i}. [{article['title']}](./{filename}.md)\n")
            
            # Create individual article files
            for article in articles:
                self._export_single_article(article, output_path)
            
            self.logger.success(f"Exported {len(articles)} articles to {output_dir}")
            
        except Exception as e:
            self.logger.error(f"Export error: {e}")

    def _export_single_article(self, article: Dict, output_path: Path):
        """Export single article to markdown"""
        try:
            filename = self._sanitize_filename(article['title'])
            filepath = output_path / f"{filename}.md"
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# {article['title']}\n\n")
                f.write(f"**Author:** {article['author']}\n")
                f.write(f"**Date:** {article['date']}\n")
                f.write(f"**Views:** {article['views']}\n")
                f.write(f"**URL:** [{article['url']}]({article['url']})\n\n")
                f.write("---\n\n")
                f.write(f"{article['content']}\n\n")
                
                # Add images
                if article['images']:
                    f.write("## Images\n\n")
                    for img_url in article['images']:
                        f.write(f"![Image]({img_url})\n")
                
                # Add comments
                if article['comments']:
                    f.write(f"\n## Comments ({len(article['comments'])})\n\n")
                    for comment in article['comments']:
                        f.write(f"**{comment['author']}** ({comment['date']})\n")
                        f.write(f"{comment['content']}\n\n")
        
        except Exception as e:
            self.logger.error(f"Error exporting article {article['title']}: {e}")

    def _sanitize_filename(self, filename: str) -> str:
        """Convert title to safe filename"""
        # Remove special characters
        safe_name = "".join(c if c.isalnum() or c in ' -_' else '' for c in filename)
        # Replace spaces with underscores
        safe_name = safe_name.replace(' ', '_')[:50]
        return safe_name or "article"


class NaverCafeCrawler:
    """Main crawler orchestrator"""
    def __init__(self, config: Dict):
        self.config = config
        self.logger = Logger("NaverCafeCrawler")
        self.authenticator = None
        self.session = None
        self.articles: List[Dict] = []
        self.stats = {
            'total_articles': 0,
            'total_comments': 0,
            'total_images': 0,
            'start_time': None,
            'end_time': None
        }

    def run(self):
        """Run the crawler"""
        try:
            self.stats['start_time'] = datetime.now()
            self.logger.info("="*50)
            self.logger.info("Naver Cafe Author Crawler Started")
            self.logger.info("="*50)
            
            # Step 1: Authenticate
            self.logger.info("Step 1: Authenticating with Naver...")
            if not self._authenticate():
                self.logger.error("Authentication failed")
                return False
            
            # Step 2: Fetch articles
            self.logger.info("Step 2: Fetching articles...")
            if not self._fetch_articles():
                self.logger.error("Failed to fetch articles")
                return False
            
            # Step 3: Export to markdown
            self.logger.info("Step 3: Exporting to markdown...")
            if not self._export_results():
                self.logger.error("Failed to export results")
                return False
            
            self.stats['end_time'] = datetime.now()
            duration = self.stats['end_time'] - self.stats['start_time']
            
            self.logger.info("="*50)
            self.logger.success("Crawling completed successfully!")
            self.logger.info(f"Total Articles: {self.stats['total_articles']}")
            self.logger.info(f"Total Comments: {self.stats['total_comments']}")
            self.logger.info(f"Duration: {duration}")
            self.logger.info("="*50)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            return False
        finally:
            self.cleanup()

    def _authenticate(self) -> bool:
        """Authenticate with Naver"""
        try:
            self.authenticator = NaverAuthenticator(
                self.config['user_id'],
                self.config['password'],
                self.logger
            )
            self.authenticator.setup_driver()
            if not self.authenticator.login():
                return False
            
            self.session = requests.Session()
            self.session.cookies.update(self.authenticator.get_cookies())
            self.logger.success("Authentication successful")
            return True
        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            return False

    def _fetch_articles(self) -> bool:
        """Fetch articles from cafe"""
        try:
            cafe_url = self.config['cafe_url']
            club_id = self.config['club_id']
            author_id = self.config['author_id']
            max_pages = self.config.get('max_pages', 10)
            period_days = self.config.get('period_days', 365)
            include_comments = self.config.get('include_comments', True)
            
            self.logger.info(f"Fetching articles by {author_id} from cafe {club_id}")
            
            cutoff_date = datetime.now() - timedelta(days=period_days)
            
            for page in range(1, max_pages + 1):
                self.logger.info(f"Fetching page {page}...")
                
                # Simulated article fetching
                articles = self._fetch_page_articles(page, club_id, author_id)
                
                if not articles:
                    self.logger.info(f"No more articles on page {page}")
                    break
                
                for article in articles:
                    try:
                        article_date = datetime.fromisoformat(article.get('date', datetime.now().isoformat()))
                        if article_date < cutoff_date:
                            continue
                        
                        self.articles.append(article)
                        self.stats['total_articles'] += 1
                        
                        if include_comments:
                            comments = self._fetch_comments(article['url'])
                            article['comments'] = comments
                            self.stats['total_comments'] += len(comments)
                        
                        self.stats['total_images'] += len(article.get('images', []))
                    
                    except Exception as e:
                        self.logger.warning(f"Error processing article: {e}")
                        continue
                
                time.sleep(1)  # Rate limiting
            
            self.logger.success(f"Fetched {self.stats['total_articles']} articles")
            return True
        
        except Exception as e:
            self.logger.error(f"Error fetching articles: {e}")
            return False

    def _fetch_page_articles(self, page: int, club_id: str, author_id: str) -> List[Dict]:
        """Fetch articles from a single page"""
        # Placeholder implementation
        return []

    def _fetch_comments(self, article_url: str) -> List[Dict]:
        """Fetch comments for an article"""
        # Placeholder implementation
        return []

    def _export_results(self) -> bool:
        """Export results to markdown"""
        try:
            exporter = MarkdownExporter(self.logger)
            output_dir = self.config.get('output_dir', 'naver_cafe_articles')
            author_name = self.config.get('author_nickname', 'Author')
            
            exporter.export_articles(self.articles, output_dir, author_name)
            return True
        except Exception as e:
            self.logger.error(f"Export error: {e}")
            return False

    def cleanup(self):
        """Cleanup resources"""
        if self.authenticator:
            self.authenticator.close()
        if self.session:
            self.session.close()


def main():
    """Main entry point"""
    config = {
        'cafe_url': 'https://cafe.naver.com/',
        'club_id': '28900532',
        'user_id': 'your_naver_id',
        'password': 'your_password',
        'author_id': 'author_id',
        'author_nickname': 'Author Name',
        'max_pages': 5,
        'period_days': 365,
        'include_comments': True,
        'output_dir': 'naver_cafe_articles'
    }
    
    crawler = NaverCafeCrawler(config)
    success = crawler.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
