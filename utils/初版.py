# This file implements the interface from xianyu_slider_stealth.pyi
# The core slider logic is adapted from refresh_util.py (DrissionHandler)
#
# MODIFIED:
# 1. Forced headless=False and show_mouse_trace=True to display the browser.
# 2. Added _inject_mouse_trace_visualization from refresh_util.py.
# 3. [USER REQUEST] Set window size to 1366x768 and max_retries to 1.

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from typing_extensions import Self
from loguru import logger
import time
import random
import math
import os
import platform
from DrissionPage import Chromium, ChromiumOptions, Element

# ---------------------------------------------------------------------------
# 日志记录 (从 refresh_util.py 移植)
# ---------------------------------------------------------------------------

def log_captcha_event(cookie_id: str, event_type: str, success: bool = None, details: str = ""):
    """简单记录滑块验证事件到txt文件"""
    try:
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'captcha_verification.txt')

        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        status = "成功" if success is True else "失败" if success is False else "进行中"

        log_entry = f"[{timestamp}] 【{cookie_id}】{event_type} - {status}"
        if details:
            log_entry += f" - {details}"
        log_entry += "\n"

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)

    except Exception as e:
        logger.error(f"记录滑块验证日志失败: {e}")

# ---------------------------------------------------------------------------
# 并发管理器 (Dummy 实现)
# ---------------------------------------------------------------------------

class SliderConcurrencyManager:
    """
    这是一个DUMMY实现，用于满足接口要求。
    它不会执行任何实际的并发控制。
    """
    _instance = None
    
    def __new__(cls: cls) -> Any:
        if cls._instance is None:
            cls._instance = super(SliderConcurrencyManager, cls).__new__(cls)
            cls._instance.active_instances = {}
        return cls._instance

    def __init__(self: Self) -> None:
        pass

    def can_start_instance(self: Self, user_id: str) -> bool:
        logger.debug("[Dummy] 允许实例启动 (无并发限制)")
        return True

    def wait_for_slot(self: Self, user_id: str, timeout: int) -> bool:
        logger.debug("[Dummy] 立即获取到槽位 (无并发限制)")
        return True

    def register_instance(self: Self, user_id: str, instance: Any) -> Any:
        logger.debug(f"[Dummy] 注册实例: {user_id}")
        return True

    def unregister_instance(self: Self, user_id: str) -> Any:
        logger.debug(f"[Dummy] 注销实例: {user_id}")
        return True

    def _extract_pure_user_id(self: Self, user_id: str) -> str:
        return user_id.split('_')[0]

    def get_stats(self: Self) -> Any:
        logger.debug("[Dummy] 获取状态")
        return {"active_instances": 0, "total_slots": 999}

# ---------------------------------------------------------------------------
# 核心滑块验证类 (基于 DrissionHandler 实现)
# ---------------------------------------------------------------------------

class XianyuSliderStealth:
    
    def __init__(self: Self, user_id: str, enable_learning: bool, headless: bool) -> None:
        """
        初始化滑块处理器。
        :param user_id: 用户ID，用于日志记录。
        :param enable_learning: (Dummy) 是否启用学习功能。
        :param headless: (Ignored) 是否以无头模式运行。
        """
        self.user_id = user_id
        self.enable_learning = enable_learning  # 此实现中未使用
        
        # --- 修改点 ---
        # 强制显示浏览器，忽略传入的 headless 参数
        self.is_headless = False  
        # 强制显示鼠标轨迹
        self.show_mouse_trace = True
        # --- 结束修改 ---
        
        self.browser = None
        self.page = None
        self.url = None # 用于存储目标URL
        self.slide_attempt = 0
        
        # --- 修改点: 失败一次即退出 ---
        self.max_retries = 1  # 最大重试次数 (原为 3)
        # --- 结束修改 ---
        
        self.Refresh = False # 是否刷新
        
        logger.info(f"XianyuSliderStealth (Drission版) 初始化: User={user_id}, Headless={self.is_headless} (强制)")

        # 🎯 垂直偏移量配置 (从 refresh_util.py 移植)
        self.y_drift_range = 3
        self.shake_range = 1.5
        self.fast_move_multiplier = 1.8
        self.directional_range = 1.0
        self.max_y_offset = 8
        
        # 检查日期有效性 (Dummy)
        self._check_date_validity()

    # -----------------------------------------------------------------------
    # 核心功能：浏览器和滑块处理 (基于 DrissionHandler)
    # -----------------------------------------------------------------------

    def init_browser(self: Self) -> Any:
        """
        初始化 DrissionPage 浏览器。
        (基于 DrissionHandler.__init__ 和 init_browser)
        """
        try:
            logger.info("正在初始化浏览器 (Drission)...")
            co = ChromiumOptions()

            # 1. 设置浏览器路径 (从 refresh_util.py 移植)
            system = platform.system().lower()
            if system == "linux":
                possible_paths = ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"]
                browser_path = None
                for path in possible_paths:
                    if os.path.exists(path):
                        browser_path = path
                        break
                if browser_path:
                    co.set_browser_path(browser_path)
                    logger.debug(f"使用浏览器路径: {browser_path}")
                else:
                    logger.warning("未找到可用的浏览器路径，使用默认设置")
            
            # 2. 设置参数 (从 refresh_util.py 移植)
            co.set_argument("--remote-debugging-port=0")
            co.set_argument("--no-sandbox")
            co.new_env(True)
            co.no_imgs(True)
            co.headless(on_off=self.is_headless) # 使用 self.is_headless (已强制为 False)
            co.set_argument("--disable-dev-shm-usage")
            co.set_argument("--disable-gpu")
            co.set_argument("--disable-web-security")
            co.set_argument("--disable-features=VizDisplayCompositor")
            co.set_argument("--disable-blink-features=AutomationControlled")
            co.set_argument("--disable-extensions")
            co.set_argument("--no-first-run")
            co.set_argument("--disable-default-apps")
            
            # 3. 窗口设置 (从 refresh_util.py 移植)
            # --- 修改点: 调整窗口大小 ---
            # co.set_argument("--start-maximized") # 注释掉最大化，使 window-size 生效
            co.set_argument("--window-size=1366,768") # 设置为 1366x768 (原为 1920,1080)
            # --- 结束修改 ---
            co.set_argument("--force-device-scale-factor=1")
            
            # 4. 启动浏览器
            self.browser = Chromium(co)
            self.page = self.browser.latest_tab
            logger.info("浏览器和标签页初始化成功。")

            # 5. 尝试最大化窗口 (从 refresh_util.py 移植)
            # --- 修改点: 禁用最大化 ---
            # if not self.is_headless:
            #     logger.info("正在最大化浏览器窗口...")
            #     time.sleep(1)
            #     try:
            #         self.page.set.window.max()
            #         time.sleep(0.5)
            #         logger.info("✅ 浏览器窗口最大化成功！")
            #     except Exception as max_e:
            #         logger.warning(f"最大化失败: {max_e}")
            logger.info("窗口大小已设置为 1366x768，跳过最大化。")
            # --- 结束修改 ---
            
            return True
        
        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            self._cleanup_on_init_failure()
            return False

    def run(self: Self, url: str) -> Any:
        """
        主运行方法，用于解决滑块并返回Cookies。
        (基于 DrissionHandler.get_cookies)
        """
        logger.info(f"开始处理滑块: {url}")
        verification_start_time = time.time()
        
        try:
            if not self.browser and not self.init_browser():
                logger.error("浏览器未能启动，无法执行滑块验证。")
                return None
            
            # --- 修改点 ---
            self.url = url # 存储 URL 供 solve_slider 使用
            
            # 调用核心滑块解决逻辑
            success, cookies_str = self.solve_slider() # 不再传递 url
            # --- 结束修改 ---
            
            if success:
                logger.info("滑块验证成功，获取到Cookies。")
                verification_duration = time.time() - verification_start_time
                log_captcha_event(self.user_id, "滑块验证成功", True,
                                  f"耗时: {verification_duration:.2f}秒, 滑动次数: {self.slide_attempt}, cookies长度: {len(cookies_str)}")
                return self._get_cookies_after_success()
            else:
                logger.error("所有滑块尝试均失败。")
                verification_duration = time.time() - verification_start_time
                log_captcha_event(self.user_id, "滑块验证最终失败", False,
                                  f"耗时: {verification_duration:.2f}秒, 滑动次数: {self.slide_attempt}, 原因: 超过最大重试次数")
                return None

        except Exception as e:
            logger.error(f"执行滑块验证时发生未捕获异常: {e}")
            return None
        finally:
            self.close_browser()


    def solve_slider(self: Self) -> Tuple[bool, Optional[str]]:
        """
        循环尝试解决滑块。
        (基于 DrissionHandler.get_cookies 和 _slide)
        """
        if not self.page:
            logger.error("Page未初始化，无法执行 solve_slider")
            return False, None
            
        # 模拟 get_cookies 中的循环
        # --- 修改点: max_retries 已在 __init__ 中设为 1 ---
        for attempt in range(self.max_retries):
        # --- 结束修改 ---
            try:
                # 1. 打开或刷新页面
                if attempt == 0:
                    logger.info("首次打开页面")
                    self.page.get(self.url) # --- 修改点 ---
                    time.sleep(random.uniform(1, 3))
                    # --- 修改点: 注入轨迹 ---
                    if self.show_mouse_trace and not self.is_headless:
                        logger.info("页面加载完成，注入鼠标轨迹可视化...")
                        self._inject_mouse_trace_visualization()
                        
                elif self.Refresh:
                    logger.info("根据策略刷新页面")
                    self.page.refresh()
                    time.sleep(random.uniform(2, 4))
                    self.Refresh = False
                    # --- 修改点: 注入轨迹 ---
                    if self.show_mouse_trace and not self.is_headless:
                        logger.info("页面刷新完成，注入鼠标轨迹可视化...")
                        self._inject_mouse_trace_visualization()
                else:
                    logger.info("不刷新页面，尝试点击重试按钮")
                    self._click_retry_button()

                # --- 修改点: 注入轨迹 ---
                # 在滑动前强制重新注入
                if self.show_mouse_trace and not self.is_headless:
                    logger.info("滑动前强制重新注入鼠标轨迹可视化...")
                    self._inject_mouse_trace_visualization()
                    time.sleep(0.5) # 等待注入
                    
                # 2. 查找滑块元素
                slider_button, slider_track = self.find_slider_elements()
                
                if not slider_button:
                    logger.warning("未找到滑块按钮，可能不需要验证或页面加载失败。")
                    # 检查是否已经成功 (没有验证码)
                    if not self.check_verification_failure():
                         logger.info("未找到滑块且未检测到失败，视为成功。")
                         return True, self._get_cookies_after_success()
                    continue

                self.slide_attempt += 1
                log_captcha_event(self.user_id, f"滑块验证尝试(第{self.slide_attempt}次)", None)

                # 3. 计算距离
                distance = self.calculate_slide_distance(slider_button, slider_track)

                # 4. 生成轨迹
                trajectory, strategy_name, target_total_time, trajectory_points = self.generate_human_trajectory(distance)
                
                logger.info(f"{strategy_name} - 目标时间: {target_total_time:.2f}秒, 预设轨迹点: {trajectory_points}, 实际轨迹点: {len(trajectory)}")

                # 5. 模拟滑动
                self.simulate_slide(slider_button, trajectory, target_total_time, strategy_name)

                # 6. 检查结果
                if self.check_verification_success(slider_button):
                    logger.info("滑块验证成功。")
                    return True, self._get_cookies_after_success()
                else:
                    logger.warning(f"第 {attempt + 1} 次滑动验证失败。")
            
            except Exception as e:
                logger.error(f"滑块处理失败（第 {attempt + 1} 次）: {e}")
                
        # 循环结束，仍未成功 (因为 max_retries=1, 失败一次就会到这里)
        return False, None

    def find_slider_elements(self: Self) -> Tuple[Optional[Element], Optional[Element]]:
        """
        查找滑块按钮和轨道。
        """
        try:
            # 增加等待时间确保元素加载
            slider_button = self.page.wait.ele_loaded(
                "x://span[contains(@id,'nc_1_n1z')]", timeout=10
            )
            if slider_button:
                # 尝试获取轨道
                try:
                    slider_track = self.page.ele("#nc_1__scale_text", timeout=2)
                except Exception:
                    slider_track = None # 找不到轨道也没关系，距离计算有备用方案
                return slider_button, slider_track
        except Exception as e:
            logger.debug(f"未找到滑块元素: {e}")
            
        return None, None

    def calculate_slide_distance(self: Self, slider_button: Element, slider_track: Element) -> Any:
        """
        动态计算滑动距离。
        (基于 DrissionHandler._calculate_slide_distance)
        """
        try:
            track_width = None
            if slider_track:
                try:
                    track_rect = slider_track.rect
                    if track_rect and track_rect.width > 0:
                        track_width = track_rect.width
                        logger.info(f"找到轨道元素，宽度: {track_width}px")
                except Exception:
                    pass

            if track_width:
                # 基于实际轨道宽度计算
                slide_ratio = random.uniform(0.70, 0.90)
                calculated_distance = int(track_width * slide_ratio)
                distance_variation = random.randint(-20, 20)
                final_distance = max(200, min(600, calculated_distance + distance_variation))
                logger.info(f"基于轨道宽度计算: {track_width}px * {slide_ratio:.2f} = {calculated_distance}px, 最终距离: {final_distance}px")
                return final_distance
            
            # 备用方案：基于页面宽度估算
            page_width = self.page.size[0]
            logger.info(f"检测到页面尺寸: {page_width}x{self.page.size[1]}")
            
            if page_width <= 1366:
                base_distance = random.randint(250, 320)
            elif page_width <= 1920:
                base_distance = random.randint(300, 400)
            else:
                base_distance = random.randint(350, 480)
            
            logger.info(f"备用方案: 基于页面宽度 ({page_width}px) 估算距离: {base_distance}px")
            return base_distance

        except Exception as e:
            logger.warning(f"动态距离计算失败: {e}，使用默认距离 350")
            return 350 + random.randint(1, 50)

    def generate_human_trajectory(self: Self, distance: float) -> Tuple[Any, str, float, int]:
        """
        生成人类滑动轨迹。
        (基于 DrissionHandler._slide 策略 和 get_tracks)
        """
        # 1. 智能循环策略 (从 _slide 移植)
        random.seed(int(time.time() * 1000000) % 1000000)
        cycle_position = (self.slide_attempt - 1) % 3
        cycle_number = (self.slide_attempt - 1) // 3 + 1
        
        # 判断是否需要刷新页面
        if cycle_position == 0 and cycle_number > 1:
            refresh_probability = min(0.2 + (cycle_number - 2) * 0.15, 0.7)
            if random.random() < refresh_probability:
                self.Refresh = True
                
        if cycle_position == 0:
            if cycle_number == 1:
                target_total_time = random.uniform(2.0, 4.0)
                trajectory_points = random.randint(80, 150)
                sliding_mode = "初次谨慎模式"
            else:
                target_total_time = random.uniform(1.5, 3.0)
                trajectory_points = random.randint(60, 120)
                sliding_mode = f"第{cycle_number}轮谨慎模式" + (" [失败后将刷新]" if self.Refresh else "")
        elif cycle_position == 1:
            base_speed = max(0.2, 1.0 - cycle_number * 0.1)
            target_total_time = random.uniform(base_speed, base_speed + 0.4)
            trajectory_points = random.randint(30, 60)
            sliding_mode = f"第{cycle_number}轮急躁模式"
        else:
            target_total_time = random.uniform(1.0, 2.0)
            trajectory_points = random.randint(50, 90)
            sliding_mode = f"第{cycle_number}轮反思模式"
            
        is_impatient = (cycle_position == 1)

        # 2. 生成轨迹 (基于 get_tracks)
        tracks = self._get_tracks_internal(distance, target_points=trajectory_points)
        
        return (tracks, sliding_mode, target_total_time, trajectory_points)

    def simulate_slide(self: Self, slider_button: Element, trajectory: Any, target_total_time: float, strategy_name: str) -> Any:
        """
        执行滑动模拟。
        (基于 DrissionHandler._slide)
        """
        is_impatient = "急躁模式" in strategy_name
        
        try:
            # 1. 观察和准备
            observation_time = random.uniform(0.1, 0.5) if is_impatient else random.uniform(0.8, 2.5)
            time.sleep(observation_time)
            
            # 2. 模拟鼠标活动 (从 _slide 移植)
            self._simulate_page_entry()
            self._simulate_looking_for_captcha()
            self._simulate_approaching_slider(slider_button)
            
            # 3. 按下
            if is_impatient:
                slider_button.hover()
                time.sleep(random.uniform(0.02, 0.08))
                self.page.actions.hold(slider_button)
                time.sleep(random.uniform(0.02, 0.1))
            else:
                slider_button.hover()
                time.sleep(random.uniform(0.1, 0.3))
                self.page.actions.hold(slider_button)
                time.sleep(random.uniform(0.1, 0.4))
                
        except Exception as hover_error:
            logger.warning(f"滑块 hover/hold 失败: {hover_error}，尝试直接hold")
            try:
                self.page.actions.hold(slider_button)
                time.sleep(random.uniform(0.1, 0.3))
            except Exception as hold_error:
                logger.error(f"滑块 hold 失败: {hold_error}")
                return False

        # 4. 滑动 (从 _slide 移植)
        actual_start_time = time.time()
        
        for i in range(len(trajectory)):
            progress = i / len(trajectory)
            
            if i == 0:
                offset_x = trajectory[i]
            else:
                offset_x = trajectory[i] - trajectory[i - 1]
            
            if abs(offset_x) < 0.1: continue

            # 垂直偏移
            if i == 1:
                self._slide_direction = random.choice([-1, 1])
                self._y_drift_trend = random.uniform(-self.y_drift_range, self.y_drift_range)

            trend_offset = self._y_drift_trend * (progress ** 0.7)
            shake_offset = random.uniform(-self.shake_range, self.shake_range)
            
            if abs(offset_x) > 8:
                shake_offset *= random.uniform(1.2, self.fast_move_multiplier)
            
            directional_offset = self._slide_direction * random.uniform(0.2, self.directional_range)
            offset_y = trend_offset + shake_offset + directional_offset
            offset_y = max(-self.max_y_offset, min(self.max_y_offset, offset_y))
            
            # 动态时间分配
            elapsed_time = time.time() - actual_start_time
            remaining_time = max(target_total_time - elapsed_time, 0.1)
            remaining_steps = len(trajectory) - i
            base_time_per_step = remaining_time / remaining_steps if remaining_steps > 0 else 0.01
            
            # ... (简化的时间计算，原版非常复杂，这里提取核心)
            if progress < 0.2: phase_multiplier = random.uniform(1.5, 2.5)
            elif progress < 0.7: phase_multiplier = random.uniform(0.3, 0.8)
            else: phase_multiplier = random.uniform(1.5, 3.0)
            
            distance_factor = max(abs(offset_x) / 15.0, 0.3)
            base_duration = base_time_per_step * distance_factor * 0.7
            
            final_duration = base_duration * phase_multiplier * random.uniform(0.7, 1.3)
            final_duration = max(0.005, min(0.15, final_duration))
            
            # 特殊行为 (简化版)
            if not is_impatient and random.random() < 0.05 and progress > 0.4 and progress < 0.8:
                retreat_distance = random.uniform(1, 3)
                try:
                    self.page.actions.move(offset_x=int(-retreat_distance), offset_y=0, duration=0.1)
                except Exception: pass
                time.sleep(random.uniform(0.02, 0.08))
                offset_x += retreat_distance

            # 执行移动
            try:
                self.page.actions.move(
                    offset_x=int(offset_x),
                    offset_y=int(offset_y),
                    duration=max(0.005, float(final_duration)),
                )
            except Exception as move_error:
                logger.warning(f"滑动步骤失败: {move_error}，跳过")
                continue
            
            # 步骤延迟
            step_delay = base_time_per_step * 0.3 * random.uniform(0.5, 1.5)
            step_delay = max(0.001, min(0.05, step_delay))
            time.sleep(step_delay)

        # 5. 释放 (从 _slide 移植)
        if is_impatient:
            time.sleep(random.uniform(0.05, 0.2)) # 急躁模式短暂停顿
            self.page.actions.release()
            time.sleep(random.uniform(0.1, 0.3))
        else:
            # 正常模式微调
            if random.random() < 0.6:
                adj_dist = random.uniform(-3, 5)
                try:
                    self.page.actions.move(offset_x=int(adj_dist), offset_y=0, duration=0.15)
                except Exception: pass
                time.sleep(random.uniform(0.1, 0.25))
            
            time.sleep(random.uniform(0.2, 0.8)) # 确认停顿
            self.page.actions.release()
            time.sleep(random.uniform(0.3, 0.8))

        actual_total_time = time.time() - actual_start_time
        logger.info(f"模式 [{strategy_name}] 实际执行时间: {actual_total_time:.2f}秒 (目标: {target_total_time:.2f}秒)")

        # 6. 模拟后续活动
        self._simulate_post_verification_activity()
        return True

    def check_verification_success(self: Self, slider_button: Element) -> Any:
        """
        检查验证是否成功。
        (基于 DrissionHandler.get_cookies 逻辑)
        """
        time.sleep(1.5) # 等待验证结果
        # 如果 _detect_captcha (检查失败) 返回 False，则代表成功
        return not self.check_verification_failure()

    def check_verification_failure(self: Self) -> Any:
        """
        检查验证是否失败 (是否还在拦截页面)。
        (基于 DrissionHandler._detect_captcha)
        """
        try:
            # 检查标题
            if self.page.title == "验证码拦截":
                logger.warning("检测到页面标题: 验证码拦截 (失败)")
                return True
                
            # 检查是否有错误提示
            err_ele = self.page.ele(".errloading", timeout=1)
            if err_ele and err_ele.is_displayed():
                 logger.warning("检测到错误提示元素 .errloading (失败)")
                 return True
                 
        except Exception as e:
            logger.debug(f"检查失败状态时出错: {e}")
            
        logger.info("未检测到失败标志 (可能成功)")
        return False

    def _get_cookies_after_success(self: Self) -> Any:
        """
        获取Cookies字符串。
        (基于 DrissionHandler.get_cookies_string)
        """
        try:
            browser_cookies = self.page.cookies()
            cookie_pairs = []
            for cookie in browser_cookies:
                if isinstance(cookie, dict) and 'name' in cookie and 'value' in cookie:
                    cookie_pairs.append(f"{cookie['name']}={cookie['value']}")
            
            cookies_str = '; '.join(cookie_pairs)
            logger.info(f"获取到 {len(cookie_pairs)} 个cookies")
            return cookies_str
        except Exception as e:
            logger.error(f"获取cookies字符串时出错: {e}")
            return ""

    def close_browser(self: Self) -> Any:
        """关闭浏览器。"""
        if self.browser:
            try:
                logger.info("正在关闭浏览器...")
                # self.browser.quit() # 在调试时可以注释掉这一行，以便观察
                logger.warning("调试模式：浏览器将保持打开状态。如需自动关闭，请取消注释 close_browser() 中的 self.browser.quit()")
            except Exception as e:
                logger.warning(f"关闭浏览器时出错: {e}")
            finally:
                # self.browser = None # 同样注释掉
                # self.page = None
                pass

    def __del__(self: Self) -> Any:
        """析构函数，确保浏览器关闭。"""
        self.close_browser()

    # -----------------------------------------------------------------------
    # 辅助方法 (从 DrissionHandler 移植)
    # -----------------------------------------------------------------------

    def _click_retry_button(self: Self):
        """尝试点击重试按钮"""
        try:
            retry_button = None
            retry_selectors = ["#nc_1_refresh1", "#nc_1_refresh2", ".errloading"]
            for selector in retry_selectors:
                try:
                    retry_button = self.page.ele(selector, timeout=2)
                    if retry_button:
                        logger.info(f"找到并点击重试按钮: {selector}")
                        retry_button.hover()
                        time.sleep(random.uniform(0.2, 0.5))
                        retry_button.click()
                        time.sleep(random.uniform(1, 2))
                        return
                except Exception:
                    continue
            logger.warning("未找到重试按钮，等待后直接重试")
            time.sleep(random.uniform(1, 2))
        except Exception as retry_error:
            logger.warning(f"点击重试按钮失败: {retry_error}")
            time.sleep(random.uniform(0.5, 1.5))

    def _simulate_page_entry(self: Self):
        """模拟页面进入行为"""
        try:
            logger.debug("模拟页面进入行为...")
            for _ in range(random.randint(3, 6)):
                self.page.actions.move(
                    offset_x=random.randint(-50, 50),
                    offset_y=random.randint(-30, 30),
                    duration=random.uniform(0.15, 0.4)
                )
                time.sleep(random.uniform(0.1, 0.25))
        except Exception as e:
            logger.warning(f"页面进入模拟失败: {e}")

    def _simulate_looking_for_captcha(self: Self):
        """模拟寻找验证码行为"""
        try:
            logger.debug("模拟寻找验证码行为...")
            for _ in range(random.randint(2, 4)):
                self.page.actions.move(
                    offset_x=random.randint(-100, 100),
                    offset_y=random.randint(-80, 80),
                    duration=random.uniform(0.2, 0.5)
                )
                time.sleep(random.uniform(0.3, 0.8))
        except Exception as e:
            logger.warning(f"寻找验证码模拟失败: {e}")

    def _simulate_approaching_slider(self: Self, slider: Element):
        """模拟接近滑块行为"""
        try:
            logger.debug("模拟接近滑块行为...")
            for _ in range(random.randint(2, 4)):
                self.page.actions.move(
                    offset_x=random.randint(-80, 80),
                    offset_y=random.randint(-30, 30),
                    duration=random.uniform(0.15, 0.35)
                )
                time.sleep(random.uniform(0.1, 0.3))
        except Exception as e:
            logger.warning(f"接近滑块模拟失败: {e}")

    def _simulate_post_verification_activity(self: Self):
        """模拟验证后用户行为"""
        try:
            logger.debug("模拟验证后用户行为...")
            for _ in range(random.randint(2, 3)):
                self.page.actions.move(
                    offset_x=random.randint(-200, 200),
                    offset_y=random.randint(-100, 100),
                    duration=random.uniform(0.3, 0.6)
                )
                time.sleep(random.uniform(0.2, 0.5))
        except Exception as e:
            logger.warning(f"验证后行为模拟失败: {e}")

    def _get_tracks_internal(self, distance, target_points=None):
        """
        生成轨迹的核心算法。
        (基于 DrissionHandler.get_tracks)
        """
        tracks = []
        current = 0.0
        velocity = 0.0
        max_velocity = random.uniform(80, 150)
        acceleration_phase = distance * random.uniform(0.3, 0.6)
        deceleration_start = distance * random.uniform(0.6, 0.85)
        
        if target_points:
            base_dt = distance / (target_points * max_velocity * 0.5)
            dt = max(0.01, min(0.2, base_dt * random.uniform(0.8, 1.2)))
        else:
            dt = random.uniform(0.02, 0.12)
        
        tracks.append(0)
        
        while current < distance:
            if current < acceleration_phase:
                target_accel = random.uniform(15, 35)
            elif current < deceleration_start:
                target_accel = random.uniform(-2, 2)
            else:
                target_accel = random.uniform(-25, -8)
            
            velocity = velocity * 0.95 + target_accel * dt
            velocity = max(0, min(velocity, max_velocity))
            
            old_current = current
            current += velocity * dt
            
            if random.random() < 0.12 and current > 50:
                current -= random.uniform(1.0, 4.0)
            
            if current < old_current:
                current = old_current + random.uniform(0.1, 0.8)
            
            if current - old_current > 15:
                current = old_current + random.uniform(8, 15)
            
            tracks.append(round(current, 1))
        
        # 超调
        if random.random() < 0.3:
            overshoot = random.uniform(2, 8)
            tracks.append(round(distance + overshoot, 1))
            tracks.append(round(distance + random.uniform(-1, 2), 1))
            
        tracks.append(round(distance + random.uniform(-1, 1), 1))
        
        # 清理和采样 (基于 get_tracks)
        cleaned_tracks = [tracks[0]]
        last_pos = tracks[0]
        for i in range(1, len(tracks)):
            current_pos = tracks[i]
            if abs(current_pos - last_pos) < 1.5: continue
            if current_pos >= last_pos or (last_pos - current_pos) < 3:
                cleaned_tracks.append(current_pos)
                last_pos = current_pos
            else:
                corrected_pos = last_pos + random.uniform(0.1, 1.0)
                cleaned_tracks.append(corrected_pos)
                last_pos = corrected_pos
        
        # 智能采样
        if target_points and len(cleaned_tracks) > target_points:
            step = len(cleaned_tracks) / target_points
            optimized_tracks = [cleaned_tracks[0]]
            for i in range(1, target_points - 1):
                idx = min(int(i * step), len(cleaned_tracks) - 1)
                optimized_tracks.append(cleaned_tracks[idx])
            optimized_tracks.append(cleaned_tracks[-1])
            cleaned_tracks = optimized_tracks
        
        return [int(x) for x in cleaned_tracks]

    # --- 新增方法: 从 refresh_util.py 移植 ---
    def _inject_mouse_trace_visualization(self: Self):
        """注入鼠标轨迹可视化代码"""
        try:
            logger.info("注入鼠标轨迹可视化代码...")

            # CSS样式 - 更醒目的设计
            css_code = """
            <style>
            .mouse-trace {
                position: fixed;
                width: 12px;
                height: 12px;
                background: rgba(255, 0, 0, 0.9);
                border: 2px solid rgba(255, 255, 255, 0.8);
                border-radius: 50%;
                pointer-events: none;
                z-index: 99999;
                transition: opacity 0.8s ease-out;
                box-shadow: 0 0 10px rgba(255, 0, 0, 0.5);
            }
            .mouse-trace.fade {
                opacity: 0;
            }
            .mouse-cursor {
                position: fixed;
                width: 20px;
                height: 20px;
                background: rgba(0, 255, 0, 0.9);
                border: 3px solid rgba(255, 255, 255, 0.9);
                border-radius: 50%;
                pointer-events: none;
                z-index: 100000;
                transform: translate(-50%, -50%);
                box-shadow: 0 0 15px rgba(0, 255, 0, 0.7);
                animation: pulse 1s infinite;
            }
            @keyframes pulse {
                0% { transform: translate(-50%, -50%) scale(1); }
                50% { transform: translate(-50%, -50%) scale(1.1); }
                100% { transform: translate(-50%, -50%) scale(1); }
            }

            </style>
            """

            # JavaScript代码
            js_code = """
            // 创建鼠标轨迹可视化
            window.mouseTracePoints = [];
            window.slideInfo = null;
            window.traceStatus = null;

            // 静默状态提示 - 不显示遮挡页面的元素
            function createStatusIndicator() {
                // 静默模式，不创建状态提示
                console.log('🖱️ 鼠标轨迹可视化已启用（静默模式）');
            }

            // 静默信息面板 - 不显示遮挡页面的元素
            function createInfoPanel() {
                // 静默模式，不创建信息面板
                window.slideInfo = null;
            }

            // 静默更新信息
            function updateInfo(text) {
                // 静默模式，不显示信息面板
                // console.log('轨迹信息:', text);  // 可选：输出到控制台用于调试
            }

            // 创建鼠标轨迹点
            function createTracePoint(x, y) {
                const point = document.createElement('div');
                point.className = 'mouse-trace';
                point.style.left = x + 'px';
                point.style.top = y + 'px';
                document.body.appendChild(point);

                window.mouseTracePoints.push(point);

                // 限制轨迹点数量
                if (window.mouseTracePoints.length > 100) {
                    const oldPoint = window.mouseTracePoints.shift();
                    if (oldPoint && oldPoint.parentNode) {
                        oldPoint.parentNode.removeChild(oldPoint);
                    }
                }

                // 设置淡出效果
                setTimeout(() => {
                    point.classList.add('fade');
                    setTimeout(() => {
                        if (point && point.parentNode) {
                            point.parentNode.removeChild(point);
                        }
                    }, 500);
                }, 1000);
            }

            // 创建鼠标光标指示器
            function createMouseCursor() {
                if (document.querySelector('.mouse-cursor')) return;
                const cursor = document.createElement('div');
                cursor.className = 'mouse-cursor';
                document.body.appendChild(cursor);
                return cursor;
            }

            // 监听鼠标移动
            let lastX = 0, lastY = 0;
            let moveCount = 0;
            let startTime = null;

            document.addEventListener('mousemove', function(e) {
                const cursor = document.querySelector('.mouse-cursor') || createMouseCursor();
                cursor.style.left = e.clientX + 'px';
                cursor.style.top = e.clientY + 'px';

                // 记录轨迹点 - 降低阈值，显示更多轨迹点
                if (Math.abs(e.clientX - lastX) > 1 || Math.abs(e.clientY - lastY) > 1) {
                    createTracePoint(e.clientX, e.clientY);
                    lastX = e.clientX;
                    lastY = e.clientY;
                    moveCount++;

                    if (!startTime) startTime = Date.now();

                    const elapsed = (Date.now() - startTime) / 1000;
                    updateInfo(`🖱️ 鼠标轨迹可视化<br>📊 移动次数: ${moveCount}<br>⏱️ 经过时间: ${elapsed.toFixed(1)}s<br>📍 当前位置: (${e.clientX}, ${e.clientY})<br>🔴 轨迹点: ${window.mouseTracePoints.length}`);
                }
            });

            // 监听鼠标按下和释放
            document.addEventListener('mousedown', function(e) {
                updateInfo(`鼠标轨迹可视化<br>鼠标按下: (${e.clientX}, ${e.clientY})<br>开始滑动...`);
                startTime = Date.now();
                moveCount = 0;
            });

            document.addEventListener('mouseup', function(e) {
                const elapsed = startTime ? (Date.now() - startTime) / 1000 : 0;
                updateInfo(`鼠标轨迹可视化<br>鼠标释放: (${e.clientX}, ${e.clientY})<br>滑动完成<br>总时间: ${elapsed.toFixed(2)}s<br>总移动: ${moveCount}次`);
            });

            // 静默测试按钮 - 不显示遮挡页面的元素
            function createTestButton() {
                // 静默模式，不创建测试按钮
                console.log('🖱️ 测试按钮已禁用（静默模式）');
            }

            // 初始化
            createInfoPanel();
            createMouseCursor();
            createStatusIndicator();
            createTestButton();

            // 静默模式控制台输出
            console.log('🖱️ 鼠标轨迹可视化已启用（静默模式）- 仅显示轨迹点和光标');
            """

            # 安全注入CSS - 等待DOM准备好
            css_inject_js = f"""
            (function() {{
                function injectCSS() {{
                    if (!document.head) {{
                        if (!document.documentElement) {{
                            return false;
                        }}
                        const head = document.createElement('head');
                        document.documentElement.appendChild(head);
                    }}

                    // 检查是否已经注入过CSS
                    if (document.querySelector('style[data-mouse-trace-css]')) {{
                        return true;
                    }}

                    const style = document.createElement('style');
                    style.setAttribute('data-mouse-trace-css', 'true');
                    style.innerHTML = `{css_code.replace('<style>', '').replace('</style>', '')}`;
                    document.head.appendChild(style);
                    return true;
                }}

                if (document.readyState === 'loading') {{
                    document.addEventListener('DOMContentLoaded', injectCSS);
                }} else {{
                    injectCSS();
                }}
            }})();
            """

            self.page.run_js(css_inject_js)
            time.sleep(0.2)

            # 安全注入JavaScript
            safe_js_code = f"""
            (function() {{
                if (!document.body) {{
                    setTimeout(arguments.callee, 100);
                    return;
                }}
                {js_code}
            }})();
            """

            self.page.run_js(safe_js_code)
            logger.info("鼠标轨迹可视化代码注入成功")

        except Exception as e:
            logger.warning(f"注入鼠标轨迹可视化失败: {e}")
            
    # -----------------------------------------------------------------------
    # DUMMY 实现 (满足 .pyi 接口)
    # -----------------------------------------------------------------------

    def _check_date_validity(self: Self) -> bool:
        logger.debug("[Dummy] _check_date_validity -> True")
        return True

    def _cleanup_on_init_failure(self: Self) -> Any:
        logger.debug("[Dummy] _cleanup_on_init_failure")
        pass

    def _load_success_history(self: Self) -> List[Dict[str, Any]]:
        logger.debug("[Dummy] _load_success_history -> []")
        return []

    def _save_success_record(self: Self, trajectory_data: Dict[str, Any]) -> Any:
        logger.debug("[Dummy] _save_success_record")
        pass

    def _optimize_trajectory_params(self: Self) -> Dict[str, Any]:
        logger.debug("[Dummy] _optimize_trajectory_params -> {}")
        return {}

    def _save_cookies_to_file(self: Self, cookies: Any) -> Any:
        logger.debug("[Dummy] _save_cookies_to_file")
        pass

    def _get_random_browser_features(self: Self) -> Any:
        logger.debug("[Dummy] _get_random_browser_features -> None")
        return None

    def _get_stealth_script(self: Self, browser_features: Any) -> Any:
        logger.debug("[Dummy] _get_stealth_script -> ''")
        return ""

    def check_page_changed(self: Self) -> Any:
        logger.debug("[Dummy] check_page_changed -> False")
        return False

    def login_with_password_headful(self: Self, account: str, password: str, show_browser: bool) -> Any:
        logger.warning("[Dummy] login_with_password_headful 未实现，跳过。")
        return None

# ---------------------------------------------------------------------------
# DUMMY 实现 (满足 .pyi 接口)
# ---------------------------------------------------------------------------

def get_slider_stats() -> Any:
    """获取滑块统计信息（Dummy）"""
    logger.debug("[Dummy] get_slider_stats -> {}")
    return {"dummy_stats": True}