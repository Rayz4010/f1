import pygame
import os
import math
import sys
import threading
import time
import traceback
import glob # Added for Map scanning

# --- PYTHON 3.11+ COMPATIBILITY FIX ---
import inspect
if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec
# --------------------------------------

import neat

pygame.init()

# Get screen info for fullscreen
info = pygame.display.Info()
SCREEN_WIDTH = info.current_w
SCREEN_HEIGHT = info.current_h
SCREEN = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("F1 NEAT Evolution")

# --- CONFIGURATION ---
UI_PERCENTAGE = 0.25
UI_WIDTH = int(SCREEN_WIDTH * UI_PERCENTAGE)
GAME_WIDTH = SCREEN_WIDTH - UI_WIDTH
TRACK_X_OFFSET = UI_WIDTH

# --- CAMERA CONFIG ---
ZOOM_FACTOR = 2.5 
CAMERA_SMOOTHING = 0.1 

# --- GLOBAL ASSETS ---
TRACK = None
scaled_width = 0
scaled_height = 0
original_width = 0
original_height = 0
CURRENT_TRACK_FILE = "track.png" # Default

def load_track_asset(filename):
    """Loads and scales the track, updating global variables."""
    global TRACK, scaled_width, scaled_height, original_width, original_height, scale, CURRENT_TRACK_FILE
    
    path = os.path.join("map", filename)
    if not os.path.exists(path):
        print(f"Warning: {filename} not found, defaulting to track.png")
        path = os.path.join("map", "track.png")
        filename = "track.png"

    try:
        temp_track = pygame.image.load(path).convert()
    except FileNotFoundError:
        print("Error: map/track.png not found. Please ensure the file exists.")
        pygame.quit()
        sys.exit()

    CURRENT_TRACK_FILE = filename
    original_width, original_height = temp_track.get_width(), temp_track.get_height()

    # Scale Track
    base_scale_x = GAME_WIDTH / original_width
    base_scale_y = SCREEN_HEIGHT / original_height
    scale = min(base_scale_x, base_scale_y) * ZOOM_FACTOR

    scaled_width = int(original_width * scale)
    scaled_height = int(original_height * scale)
    TRACK = pygame.transform.scale(temp_track, (scaled_width, scaled_height))

# Initial Load
load_track_asset("track.png")

# Fonts
try:
    FONT_MAIN = pygame.font.SysFont("Consolas", int(18), bold=True)
    FONT_HEADER = pygame.font.SysFont("Arial", int(20), bold=True)
    FONT_MENU = pygame.font.SysFont("Arial", 40, bold=True) # New Font for Menu
    FONT_NET = pygame.font.SysFont("Arial", 12)
    FONT_ERROR = pygame.font.SysFont("Arial", 24, bold=True)
except:
    FONT_MAIN = pygame.font.SysFont(None, 22)
    FONT_HEADER = pygame.font.SysFont(None, 24)
    FONT_MENU = pygame.font.SysFont(None, 50)
    FONT_NET = pygame.font.SysFont(None, 14)
    FONT_ERROR = pygame.font.SysFont(None, 30)

quit_flag = False
manual_reset = False
show_telemetry = False
show_network = False 

# BUTTONS
BUTTON_PADDING = 20
BUTTON_WIDTH = 140
BUTTON_HEIGHT = 48

EXIT_BUTTON_RECT = pygame.Rect(SCREEN_WIDTH - BUTTON_WIDTH - BUTTON_PADDING, BUTTON_PADDING, BUTTON_WIDTH, BUTTON_HEIGHT)
RESET_BUTTON_RECT = pygame.Rect(SCREEN_WIDTH - (BUTTON_WIDTH * 2) - (BUTTON_PADDING * 2), BUTTON_PADDING, BUTTON_WIDTH, BUTTON_HEIGHT)

# Colors
EXIT_BUTTON_COLOR = (200, 0, 0)
RESET_BUTTON_COLOR = (255, 140, 0) 
EXIT_BUTTON_BORDER_COLOR = (255, 255, 255)
BUTTON_TEXT_COLOR = (255, 255, 255)
COLOR_UI_BG = (30, 30, 30)     
COLOR_TEXT_WHITE = (255, 255, 255)
COLOR_TEXT_GREY = (150, 150, 150)
COLOR_PURPLE = (218, 112, 214) 
COLOR_GREEN = (0, 200, 0)      
COLOR_RED = (200, 50, 50)
COLOR_BLUE = (0, 191, 255)

BEST_OVERALL_LAP = float('inf')

def format_time(ms):
    minutes = int(ms // 60000)
    seconds = int((ms % 60000) // 1000)
    milliseconds = int(ms % 1000)
    return f"{minutes}:{seconds:02}.{milliseconds:03}"

def draw_rounded_button(surface, color, rect, text_surf):
    """Draws a button with rounded corners."""
    pygame.draw.rect(surface, color, rect, border_radius=12)
    pygame.draw.rect(surface, (255, 255, 255), rect, 2, border_radius=8)
    text_rect = text_surf.get_rect(center=rect.center)
    surface.blit(text_surf, text_rect)
    
def draw_chamfered_button(surface, color, rect, text_surf):
    """Draws a button with chamfered (cut) corners."""
    x, y, w, h = rect
    chamfer = 12 
    points = [
        (x + chamfer, y), (x + w - chamfer, y), (x + w, y + chamfer),
        (x + w, y + h - chamfer), (x + w - chamfer, y + h), (x + chamfer, y + h),
        (x, y + h - chamfer), (x, y + chamfer)
    ]
    pygame.draw.polygon(surface, color, points)
    text_rect = text_surf.get_rect(center=rect.center)
    surface.blit(text_surf, text_rect)
    
def draw_ui_buttons(surface):
    label_exit = FONT_MAIN.render("Exit", True, BUTTON_TEXT_COLOR)
    draw_chamfered_button(surface, EXIT_BUTTON_COLOR, EXIT_BUTTON_RECT, label_exit)
    label_reset = FONT_MAIN.render("Reset", True, BUTTON_TEXT_COLOR)
    draw_chamfered_button(surface, RESET_BUTTON_COLOR, RESET_BUTTON_RECT, label_reset)
    
def _monitor_buttons_thread():
    global manual_reset, quit_flag
    pressed = False
    while True:
        if quit_flag: break
        try:
            if not pygame.get_init(): break
            mouse_pressed = pygame.mouse.get_pressed(num_buttons=3)
            if mouse_pressed[0]:
                if not pressed:
                    pressed = True
                    mx, my = pygame.mouse.get_pos()
                    if EXIT_BUTTON_RECT.collidepoint(mx, my):
                        pygame.event.post(pygame.event.Event(pygame.QUIT))
                    if RESET_BUTTON_RECT.collidepoint(mx, my):
                        manual_reset = True
            else:
                pressed = False
        except: break
        time.sleep(0.05)

threading.Thread(target=_monitor_buttons_thread, daemon=True).start()

# --- NEW PAUSE MENU SYSTEM ---
def draw_centered_text(screen, text, font, color, y_offset=0):
    surf = font.render(text, True, color)
    rect = surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + y_offset))
    screen.blit(surf, rect)

def handle_pause_menu(screen):
    global manual_reset, quit_flag
    paused = True
    menu_state = "main" # main, maps, instructions
    
    # Snapshot of screen for background
    bg_copy = screen.copy()
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    overlay.fill((0, 0, 0))
    overlay.set_alpha(200)

    while paused:
        # Re-draw background every frame so interactions look clean
        screen.blit(bg_copy, (0,0))
        screen.blit(overlay, (0,0))
        
        mx, my = pygame.mouse.get_pos()
        click = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if menu_state == "main":
                        paused = False
                    else:
                        menu_state = "main"
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    click = True

        if menu_state == "main":
            # Title
            draw_centered_text(screen, "PAUSED", FONT_MENU, COLOR_TEXT_WHITE, -150)
            
            # Buttons
            btn_w, btn_h = 300, 60
            center_x = SCREEN_WIDTH // 2 - btn_w // 2
            
            # 1. Maps
            btn_maps = pygame.Rect(center_x, SCREEN_HEIGHT // 2 - 50, btn_w, btn_h)
            color_maps = COLOR_PURPLE if btn_maps.collidepoint((mx, my)) else (80, 80, 80)
            draw_rounded_button(screen, color_maps, btn_maps, FONT_HEADER.render("Maps", True, COLOR_TEXT_WHITE))
            
            # 2. Instructions
            btn_instr = pygame.Rect(center_x, SCREEN_HEIGHT // 2 + 30, btn_w, btn_h)
            color_instr = COLOR_BLUE if btn_instr.collidepoint((mx, my)) else (80, 80, 80)
            draw_rounded_button(screen, color_instr, btn_instr, FONT_HEADER.render("Instructions", True, COLOR_TEXT_WHITE))
            
            # 3. Exit
            btn_exit = pygame.Rect(center_x, SCREEN_HEIGHT // 2 + 110, btn_w, btn_h)
            color_exit = COLOR_RED if btn_exit.collidepoint((mx, my)) else (80, 80, 80)
            draw_rounded_button(screen, color_exit, btn_exit, FONT_HEADER.render("Exit Game", True, COLOR_TEXT_WHITE))
            
            # 4. Resume (Small text below)
            draw_centered_text(screen, "Press ESC to Resume", FONT_MAIN, COLOR_TEXT_GREY, 200)

            if click:
                if btn_maps.collidepoint((mx, my)): menu_state = "maps"
                if btn_instr.collidepoint((mx, my)): menu_state = "instructions"
                if btn_exit.collidepoint((mx, my)): 
                    pygame.quit()
                    sys.exit()

        elif menu_state == "maps":
            draw_centered_text(screen, "SELECT MAP", FONT_MENU, COLOR_TEXT_WHITE, -200)
            
            # Find map files in assets
            map_files = glob.glob(os.path.join("map", "*.png"))
            map_files = [os.path.basename(f) for f in map_files if "car" not in f] # Exclude car.png
            if not map_files: map_files = ["track.png"]
            
            start_y = SCREEN_HEIGHT // 2 - 100
            for i, f_name in enumerate(map_files):
                btn_rect = pygame.Rect(SCREEN_WIDTH//2 - 150, start_y + (i * 50), 300, 40)
                
                # Highlight current map
                is_current = (f_name == CURRENT_TRACK_FILE)
                col = COLOR_GREEN if is_current else (60, 60, 60)
                if btn_rect.collidepoint((mx, my)): col = COLOR_PURPLE
                
                draw_rounded_button(screen, col, btn_rect, FONT_MAIN.render(f_name, True, COLOR_TEXT_WHITE))
                
                if click and btn_rect.collidepoint((mx, my)):
                    load_track_asset(f_name)
                    manual_reset = True # Restart generation
                    paused = False # Close menu
            
            back_rect = pygame.Rect(SCREEN_WIDTH//2 - 50, SCREEN_HEIGHT - 100, 100, 40)
            draw_rounded_button(screen, (100, 100, 100), back_rect, FONT_MAIN.render("Back", True, COLOR_TEXT_WHITE))
            if click and back_rect.collidepoint((mx, my)): menu_state = "main"

        elif menu_state == "instructions":
            draw_centered_text(screen, "INSTRUCTIONS", FONT_MENU, COLOR_TEXT_WHITE, -200)
            
            lines = [
                "Goal: The AI must learn to drive around the track.",
                "Generation: Cars evolve over time using NEAT.",
                "Controls:",
                "- ESC: Open this menu",
                "- I: Toggle Telemetry Panel",
                "- N: Toggle Neural Network View",
                "- R / Reset Button: Force new generation",
                "",
                "Green Lines = Vision Sensors",
                "Red/Green Panel = Control Inputs"
            ]
            
            for i, line in enumerate(lines):
                draw_centered_text(screen, line, FONT_HEADER, COLOR_TEXT_WHITE, -120 + (i * 30))
                
            back_rect = pygame.Rect(SCREEN_WIDTH//2 - 50, SCREEN_HEIGHT - 100, 100, 40)
            draw_rounded_button(screen, (100, 100, 100), back_rect, FONT_MAIN.render("Back", True, COLOR_TEXT_WHITE))
            if click and back_rect.collidepoint((mx, my)): menu_state = "main"

        pygame.display.update()

class Car(pygame.sprite.Sprite):
    def __init__(self, car_id):
        super().__init__()
        self.car_id = car_id
        try:
            self.original_image = pygame.image.load(os.path.join("assets", "car.png")).convert_alpha()
        except FileNotFoundError:
            self.original_image = pygame.Surface((30, 50))
            self.original_image.fill((255, 0, 0))

        car_scale = scale * 0.2
        self.original_image = pygame.transform.scale(self.original_image, (int(self.original_image.get_width() * car_scale), int(self.original_image.get_height() * car_scale)))
        self.image = self.original_image
        
        # Start Pos adjusted for scaling ratio relative to original designed track
        self.start_pos = (490 * (scaled_width / original_width), 820 * (scaled_height / original_height))
        
        self.rect = self.image.get_rect(center=self.start_pos)
        self.vel_vector = pygame.math.Vector2(0.8, 0)
        self.angle = 0
        self.rotation_vel = 7 * (ZOOM_FACTOR * 0.8) 
        self.alive = True
        self.radars = []
        self.lap_started = False
        self.lap_completed = False
        self.current_lap_time = 0
        self.lap_start_time = 0
        self.lap_times = []
        self.personal_best = float('inf')
        self.speed = 2.0 
        self.max_speed = 35 * (ZOOM_FACTOR * 0.8) 
        self.scale = scale
        self.last_pos = pygame.math.Vector2(self.rect.center)
        self.stuck_frames = 0
        self.distance_travelled = 0.0
        self.time_alive = 0 
        
        self.current_steer = 0.0
        self.target_steer = 0.0
        self.current_accel = 0.0
        self.target_accel = 0.0
        self.current_brake = 0.0
        self.target_brake = 0.0
        
        self.STEER_SMOOTHING = 1.0 
        self.ACCEL_SMOOTHING = 1.0

    def update(self, is_leader=False):
        self.time_alive += 1
        
        # Auto Launch (First 0.5s)
        if self.time_alive < 30:
            self.target_accel = 1.0
            self.target_brake = 0.0

        self.smooth_controls()
        self.radars.clear()
        self.drive()
        self.check_lap()
        self.rotate()
        
        if is_leader: self.image.set_alpha(255) 
        else: self.image.set_alpha(100)

        for radar_angle in (-60, -30, 0, 30, 60):
            self.radar(radar_angle, draw=is_leader)
            
        self.collision()
        
        # Rules
        if self.time_alive > 240 and self.speed < 0.5: self.alive = False
        if abs(self.current_steer) > 0.8 and self.speed < 3.0 and self.time_alive > 120: self.alive = False
            
        current_pos = pygame.math.Vector2(self.rect.center)
        moved_dist = (current_pos - self.last_pos).length()

        if moved_dist < 0.5: self.stuck_frames += 1
        else: self.stuck_frames = 0
        self.last_pos = current_pos

        if self.stuck_frames > 90: self.alive = False

        self.data()

    def smooth_controls(self):
        self.current_steer += (self.target_steer - self.current_steer) * self.STEER_SMOOTHING
        self.current_accel += (self.target_accel - self.current_accel) * self.ACCEL_SMOOTHING
        self.current_brake += (self.target_brake - self.current_brake) * self.ACCEL_SMOOTHING

    def drive(self):
        torque = 0.5 
        if self.speed > 15: torque = 0.15 

        self.speed += (self.current_accel * torque)
        brake_power = 0.3
        if self.speed < 5: brake_power = 0.05
            
        self.speed -= (self.current_brake * brake_power) 
        self.speed *= 0.99 
        self.speed = max(0, min(self.max_speed, self.speed))
        self.rect.center += self.vel_vector * self.speed
        self.distance_travelled += self.speed   

    def check_lap(self):
        global BEST_OVERALL_LAP
        if self.lap_started and self.alive:
             self.current_lap_time = pygame.time.get_ticks() - self.lap_start_time

        if not self.lap_started:
            if math.sqrt((self.rect.center[0] - self.start_pos[0])**2 + (self.rect.center[1] - self.start_pos[1])**2) > 50 * self.scale:
                self.lap_started = True
                self.lap_start_time = pygame.time.get_ticks()
        
        if self.lap_started and not self.lap_completed:
            if math.sqrt((self.rect.center[0] - self.start_pos[0])**2 + (self.rect.center[1] - self.start_pos[1])**2) < 50 * self.scale:
                self.lap_completed = True
                final_time = pygame.time.get_ticks() - self.lap_start_time
                self.lap_times.append(final_time)
                if final_time < self.personal_best: self.personal_best = final_time
                if final_time < BEST_OVERALL_LAP: BEST_OVERALL_LAP = final_time
                self.max_speed = min(self.max_speed + 5, 100) 
                self.lap_started = False
                self.lap_completed = False
                self.lap_start_time = 0
                self.current_lap_time = 0

    def collision(self):
        length = 40 * self.scale
        right_pt = [int(self.rect.center[0] + math.cos(math.radians(self.angle + 18)) * length),
                    int(self.rect.center[1] - math.sin(math.radians(self.angle + 18)) * length)]
        left_pt  = [int(self.rect.center[0] + math.cos(math.radians(self.angle - 18)) * length),
                    int(self.rect.center[1] - math.sin(math.radians(self.angle - 18)) * length)]

        max_w, max_h = TRACK.get_width(), TRACK.get_height()
        def is_collision(pt):
            if pt[0] < 0 or pt[0] >= max_w or pt[1] < 0 or pt[1] >= max_h: return True
            try:
                # Assuming Green (2, 105, 31) is tarmac/safe area
                return TRACK.get_at(pt) == pygame.Color(2, 105, 31, 255)
            except: return True

        if is_collision(right_pt) or is_collision(left_pt):
            self.alive = False

    def rotate(self):
        turn_amount = self.rotation_vel * self.current_steer
        self.angle -= turn_amount
        self.vel_vector = pygame.math.Vector2(0.8, 0).rotate(-self.angle)
        self.image = pygame.transform.rotozoom(self.original_image, self.angle, 1)
        self.rect = self.image.get_rect(center=self.rect.center)

    def radar(self, radar_angle, draw=True):
        length = 0
        x = int(self.rect.center[0])
        y = int(self.rect.center[1])
        max_w, max_h = TRACK.get_width(), TRACK.get_height()

        while length < 300 * self.scale:
            if x < 0 or x >= max_w or y < 0 or y >= max_h: break
            try:
                if TRACK.get_at((x, y)) == pygame.Color(2, 105, 31, 255): break
            except IndexError: break
            length += 1
            x = int(self.rect.center[0] + math.cos(math.radians(self.angle + radar_angle)) * length)
            y = int(self.rect.center[1] - math.sin(math.radians(self.angle + radar_angle)) * length)

        dist = int(math.sqrt(math.pow(self.rect.center[0] - x, 2) + math.pow(self.rect.center[1] - y, 2)))
        self.radars.append([radar_angle, dist, (x, y)])

    def data(self):
            input_data = [0, 0, 0, 0, 0, 0]
            for i, radar in enumerate(self.radars):
                normalized_dist = int(radar[1]) / (300.0 * self.scale)
                input_data[i] = 1.0 - max(0.0, min(1.0, normalized_dist))
            input_data[5] = self.speed / self.max_speed
            return input_data

def draw_f1_leaderboard(screen, cars):
    COLOR_HEADER_BG = (215, 80, 65)
    COLOR_ROW_BG = (28, 32, 38)
    COLOR_ROW_ALT = (34, 38, 45)
    COLOR_TEXT_MAIN = (240, 240, 240)
    COLOR_TEXT_DIM = (150, 150, 150)
    
    start_x = 0
    start_y = 0
    header_height = 45
    row_height = 36
    
    active_cars = [group.sprite for group in cars if group.sprite.alive]
    active_cars.sort(key=lambda x: x.distance_travelled, reverse=True)
    
    pygame.draw.rect(screen, COLOR_ROW_BG, (0, 0, UI_WIDTH, SCREEN_HEIGHT))

    header_rect = pygame.Rect(start_x, start_y, UI_WIDTH, header_height)
    pygame.draw.rect(screen, COLOR_HEADER_BG, header_rect)
    
    title_surf = FONT_HEADER.render("LEADERBOARD", True, (255, 255, 255))
    title_rect = title_surf.get_rect(midleft=(start_x + 15, start_y + header_height // 2))
    screen.blit(title_surf, title_rect)

    max_rows = int((SCREEN_HEIGHT - header_height) / row_height)
    
    for i, car in enumerate(active_cars[:max_rows]):
        curr_y = header_height + (i * row_height)
        if i % 2 == 1:
            pygame.draw.rect(screen, COLOR_ROW_ALT, (start_x, curr_y, UI_WIDTH, row_height))
            
        text_y_center = curr_y + (row_height // 2)
        
        rank_txt = FONT_MAIN.render(str(i + 1), True, COLOR_TEXT_MAIN)
        rank_rect = rank_txt.get_rect(midleft=(start_x + 15, text_y_center))
        screen.blit(rank_txt, rank_rect)
        
        car_name_txt = FONT_MAIN.render(f"CAR {car.car_id}", True, COLOR_TEXT_MAIN)
        car_rect = car_name_txt.get_rect(midleft=(start_x + 50, text_y_center))
        screen.blit(car_name_txt, car_rect)
        
        lap_count = len(car.lap_times)
        lap_txt = FONT_NET.render(f"L{lap_count}", True, COLOR_TEXT_DIM)
        lap_rect = lap_txt.get_rect(midleft=(start_x + 150, text_y_center))
        screen.blit(lap_txt, lap_rect)
        
        if car.lap_times: t_str = format_time(car.lap_times[-1])
        else: t_str = format_time(car.current_lap_time)
            
        time_txt = FONT_MAIN.render(t_str, True, COLOR_TEXT_MAIN)
        time_rect = time_txt.get_rect(midright=(UI_WIDTH - 15, text_y_center))
        screen.blit(time_txt, time_rect)

def draw_telemetry_panel(screen, cars):
    panel_width = 230
    row_height = 30
    header_height = 30
    needed_height = (len(cars) * row_height) + header_height + 10
    total_height = min(needed_height, SCREEN_HEIGHT - 50)
    start_x = SCREEN_WIDTH - panel_width - 20
    start_y = SCREEN_HEIGHT - total_height - 20
    s = pygame.Surface((panel_width, total_height))
    s.set_alpha(220)
    s.fill((20, 20, 20))
    screen.blit(s, (start_x, start_y))
    pygame.draw.rect(screen, (200, 0, 0), (start_x, start_y, panel_width, header_height))
    header_text = FONT_MAIN.render("LIVE TELEMETRY", True, COLOR_TEXT_WHITE)
    screen.blit(header_text, (start_x + 10, start_y + 5))
    visible_cars = int((total_height - header_height - 10) / row_height)
    for i in range(min(len(cars), visible_cars)):
        car_group = cars[i]
        car = car_group.sprite
        y_pos = start_y + header_height + (i * row_height) + 5
        id_text = FONT_MAIN.render(f"{car.car_id}", True, COLOR_TEXT_WHITE if car.alive else COLOR_TEXT_GREY)
        screen.blit(id_text, (start_x + 10, y_pos))
        telemetry_x = start_x + 50 
        bar_max_width = 35 
        bar_height = 6 
        if car.alive:
            accel_val = max(0, min(1, car.current_accel))
            accel_width = accel_val * bar_max_width
            pygame.draw.rect(screen, (0, 80, 0), (telemetry_x, y_pos + 8, bar_max_width, bar_height), 1)
            pygame.draw.rect(screen, COLOR_GREEN, (telemetry_x, y_pos + 8, accel_width, bar_height))
            brake_x = telemetry_x + bar_max_width + 4
            brake_val = max(0, min(1, car.current_brake))
            brake_width = brake_val * bar_max_width
            pygame.draw.rect(screen, (80, 0, 0), (brake_x, y_pos + 8, bar_max_width, bar_height), 1)
            pygame.draw.rect(screen, COLOR_RED, (brake_x, y_pos + 8, brake_width, bar_height))
            steer_y = y_pos + 18
            total_steer_width = (bar_max_width * 2) + 4
            center_x = telemetry_x + (total_steer_width / 2)
            pygame.draw.line(screen, (100,100,100), (telemetry_x, steer_y + bar_height/2), (telemetry_x + total_steer_width, steer_y + bar_height/2), 1)
            pygame.draw.line(screen, (200,200,200), (center_x, steer_y), (center_x, steer_y + bar_height), 1)
            steer = max(-1, min(1, car.current_steer))
            steer_pixels = steer * (total_steer_width / 2)
            if steer_pixels > 0:
                pygame.draw.rect(screen, COLOR_BLUE, (center_x, steer_y, steer_pixels, bar_height))
            else:
                pygame.draw.rect(screen, COLOR_BLUE, (center_x + steer_pixels, steer_y, abs(steer_pixels), bar_height))

def draw_chase_cam(screen, leader):
    global EXIT_BUTTON_RECT, RESET_BUTTON_RECT
    CAM_SIZE = 250
    ZOOM = 2.0
    VIEW_SIZE = CAM_SIZE / ZOOM
    cam_x = SCREEN_WIDTH - CAM_SIZE - 20
    cam_y = 20 
    lens = pygame.Surface((int(VIEW_SIZE), int(VIEW_SIZE)))
    lens.fill((30, 30, 30))
    if leader:
        offset_x = -leader.rect.centerx + (VIEW_SIZE / 2)
        offset_y = -leader.rect.centery + (VIEW_SIZE / 2)
        lens.blit(TRACK, (offset_x, offset_y))
        car_draw_pos = (int(VIEW_SIZE/2 - leader.image.get_width()/2), int(VIEW_SIZE/2 - leader.image.get_height()/2))
        lens.blit(leader.image, car_draw_pos)

    final_view = pygame.transform.scale(lens, (int(CAM_SIZE), int(CAM_SIZE)))
    screen.blit(final_view, (cam_x, cam_y))
    pygame.draw.rect(screen, (255, 255, 255), (cam_x - 2, cam_y - 2, CAM_SIZE + 4, CAM_SIZE + 4), 2)
    
    btn_w = 70
    btn_h = 28
    padding = 8
    
    exit_x = cam_x + CAM_SIZE - btn_w - padding
    exit_y = cam_y + padding
    EXIT_BUTTON_RECT = pygame.Rect(exit_x, exit_y, btn_w, btn_h)
    label_exit = FONT_MAIN.render("EXIT", True, (255, 255, 255))
    draw_rounded_button(screen, (200, 50, 50), EXIT_BUTTON_RECT, label_exit)
    
    reset_x = exit_x - btn_w - padding
    reset_y = cam_y + padding
    RESET_BUTTON_RECT = pygame.Rect(reset_x, reset_y, btn_w, btn_h)
    label_reset = FONT_MAIN.render("RESET", True, (255, 255, 255))
    draw_rounded_button(screen, (220, 120, 0), RESET_BUTTON_RECT, label_reset)

def draw_neural_network(screen, genome, config, car, inputs, outputs):
    panel_w = 520
    panel_h = 300
    panel_x = SCREEN_WIDTH - panel_w - 20 
    panel_y = SCREEN_HEIGHT - panel_h - 20
    
    COLOR_BG = (30, 33, 40)
    COLOR_DIVIDER = (60, 65, 75)
    COLOR_ACCENT_GREEN = (80, 220, 120)
    COLOR_ACCENT_RED = (220, 80, 80)
    COLOR_BAR_BG = (50, 55, 60)
    COLOR_YELLOW = (240, 220, 80)
    
    s = pygame.Surface((panel_w, panel_h))
    s.set_alpha(240)
    s.fill(COLOR_BG)
    screen.blit(s, (panel_x, panel_y))
    pygame.draw.rect(screen, (200, 200, 200), (panel_x, panel_y, panel_w, panel_h), 1)

    header_text = FONT_HEADER.render(f"NEURAL NETWORK - Car {car.car_id}", True, (255, 255, 255))
    screen.blit(header_text, (panel_x + 15, panel_y + 10))

    graph_width = 240
    divider_x = panel_x + graph_width
    pygame.draw.line(screen, COLOR_DIVIDER, (divider_x, panel_y + 40), (divider_x, panel_y + panel_h - 20), 2)
    
    input_nodes = [-1, -2, -3, -4, -5, -6] 
    output_nodes = [0, 1, 2, 3]
    
    node_positions = {}
    node_values = {} 
    layer_h = panel_h - 60
    
    for i, node_key in enumerate(input_nodes):
        x = panel_x + 40
        y = panel_y + 60 + (i * (layer_h / len(input_nodes)))
        node_positions[node_key] = (int(x), int(y))
        
        val = inputs[i] if i < len(inputs) else 0.0
        node_values[node_key] = val

        lbl = f"S{i}" if i < 5 else "SPD"
        label = FONT_NET.render(lbl, True, (150, 150, 150))
        screen.blit(label, (x - 25, y - 5))
        
        color = COLOR_ACCENT_GREEN if val > 0.1 else (80, 80, 80)
        pygame.draw.circle(screen, color, (int(x), int(y)), 6)

    output_labels = ["L", "R", "B", "G"]
    for i, node_key in enumerate(output_nodes):
        x = divider_x - 40
        y = panel_y + 80 + (i * (layer_h / len(output_nodes)))
        node_positions[node_key] = (int(x), int(y))
        
        label = FONT_NET.render(output_labels[i], True, (150, 150, 150))
        screen.blit(label, (x + 15, y - 5))
        
        val = outputs[i] if i < len(outputs) else 0
        color = COLOR_ACCENT_GREEN if val > 0.5 else (80, 80, 80)
        pygame.draw.circle(screen, color, (int(x), int(y)), 6)

    for cg in genome.connections.values():
        if not cg.enabled: continue
        in_node, out_node = cg.key
        input_val = node_values.get(in_node, 1.0)
        if input_val < 0.01: continue 

        if in_node in node_positions and out_node in node_positions:
            start = node_positions[in_node]
            end = node_positions[out_node]
            color = COLOR_ACCENT_GREEN if cg.weight > 0 else COLOR_ACCENT_RED
            width = max(1, min(2, int(abs(cg.weight))))
            pygame.draw.line(screen, color, start, end, width)

    bar_start_x = divider_x + 20
    current_y = panel_y + 50
    screen.blit(FONT_MAIN.render("Vision Sensors", True, (255, 255, 255)), (bar_start_x, current_y))
    current_y += 25
    angles = ["-60°", "-30°", "0°", "30°", "60°"]
    for i, angle_text in enumerate(angles):
        screen.blit(FONT_NET.render(angle_text, True, (180, 180, 180)), (bar_start_x, current_y + 2))
        bg_rect = pygame.Rect(bar_start_x + 40, current_y + 5, 140, 8)
        pygame.draw.rect(screen, COLOR_BAR_BG, bg_rect, border_radius=4)
        val = inputs[i] if i < len(inputs) else 0
        fill_width = int(val * 140)
        if fill_width > 0:
            pygame.draw.rect(screen, COLOR_ACCENT_GREEN, (bar_start_x + 40, current_y + 5, fill_width, 8), border_radius=4)
        current_y += 18
    current_y += 10
    screen.blit(FONT_MAIN.render("Controls", True, (255, 255, 255)), (bar_start_x, current_y))
    current_y += 25
    steer_val = (car.target_steer + 1) / 2
    controls = [
        ("STR", steer_val, COLOR_ACCENT_GREEN),
        ("GAS", car.target_accel, COLOR_ACCENT_GREEN),
        ("BRK", car.target_brake, COLOR_ACCENT_RED),
    ]
    for label, val, col in controls:
        screen.blit(FONT_NET.render(label, True, (180, 180, 180)), (bar_start_x, current_y + 2))
        bg_rect = pygame.Rect(bar_start_x + 40, current_y + 5, 140, 8)
        pygame.draw.rect(screen, COLOR_BAR_BG, bg_rect, border_radius=4)
        fill_width = int(max(0, min(1, val)) * 140)
        if fill_width > 0:
            pygame.draw.rect(screen, col, (bar_start_x + 40, current_y + 5, fill_width, 8), border_radius=4)
        current_y += 18
    screen.blit(FONT_NET.render("SPD", True, (180, 180, 180)), (bar_start_x, current_y + 2))
    bg_rect = pygame.Rect(bar_start_x + 40, current_y + 5, 140, 8)
    pygame.draw.rect(screen, COLOR_BAR_BG, bg_rect, border_radius=4)
    speed_norm = car.speed / car.max_speed
    fill_width = int(max(0, min(1, speed_norm)) * 140)
    if fill_width > 0:
        pygame.draw.rect(screen, COLOR_YELLOW, (bar_start_x + 40, current_y + 5, fill_width, 8), border_radius=4)
        pygame.draw.circle(screen, COLOR_YELLOW, (bar_start_x + 40 + fill_width, current_y + 9), 5)
        
def eval_genomes(genomes, config):
    global quit_flag, BEST_OVERALL_LAP, show_telemetry, manual_reset, show_network
    manual_reset = False 
    
    cars = []
    nets = []
    
    BEST_OVERALL_LAP = float('inf')
    
    car_id_counter = 1
    for _, genome in genomes:
        car_group = pygame.sprite.GroupSingle(Car(car_id_counter))
        cars.append(car_group)
        net = neat.nn.FeedForwardNetwork.create(genome, config)
        nets.append(net)
        genome.fitness = 0
        car_id_counter += 1
        
    clock = pygame.time.Clock()
    start_time = pygame.time.get_ticks()
    cam_x = 0
    cam_y = 0
    run = True
    
    while run:
        if manual_reset: run = False
        if (pygame.time.get_ticks() - start_time) > 600000: run = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_flag = True
                run = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_i: show_telemetry = not show_telemetry
                if event.key == pygame.K_n: show_network = not show_network
                
                # --- MENU TRIGGER ---
                if event.key == pygame.K_ESCAPE:
                    handle_pause_menu(SCREEN)
                    # If menu caused a manual reset (new map), break loop
                    if manual_reset: run = False

        alive_cars = [c.sprite for c in cars if c.sprite.alive]
        leader = None
        leader_genome = None
        leader_inputs = []
        leader_outputs = []
        
        if alive_cars:
            best_dist = -1
            for idx, c_group in enumerate(cars):
                c = c_group.sprite
                if c.alive and c.distance_travelled > best_dist:
                    best_dist = c.distance_travelled
                    leader = c
                    leader_genome = genomes[idx][1]

        for i, car_group in enumerate(cars):
            car = car_group.sprite
            if not car.alive: continue

            car_inputs = car.data()
            if len(car_inputs) > len(nets[i].input_nodes):
                car_inputs = car_inputs[:len(nets[i].input_nodes)]

            if car.time_alive < 30:
                 raw = [0, 0, 0, 0]
            else:
                 raw = nets[i].activate(car_inputs)
                 while len(raw) < 4: raw = list(raw) + [0.0]

            if car == leader:
                leader_inputs = car_inputs
                leader_outputs = raw

            if car.time_alive >= 30:
                steer_left  = raw[0]
                steer_right = raw[1]
                target_steer = steer_right - steer_left
                if abs(target_steer) < 0.2: target_steer = 0.0
                car.target_steer = max(-1.0, min(1.0, target_steer))
                car.target_brake = max(0.0, min(1.0, (raw[2] + 1) / 2.0))
                car.target_accel = max(0.0, min(1.0, (raw[3] + 1) / 2.0))

            is_leader = (car == leader)
            car.update(is_leader=is_leader)

            if math.isfinite(car.speed):
                genomes[i][1].fitness += car.speed * 0.1
                if car.speed > 5:
                    genomes[i][1].fitness += (car.speed ** 1.5) * 0.05

            if car.time_alive > 100 and car.speed < 2:
                genomes[i][1].fitness -= 2 
                car.alive = False

        if leader:
            game_center_x = UI_WIDTH + (GAME_WIDTH / 2)
            game_center_y = SCREEN_HEIGHT / 2
            target_cam_x = leader.rect.centerx - game_center_x
            target_cam_y = leader.rect.centery - game_center_y
            cam_x += (target_cam_x - cam_x) * CAMERA_SMOOTHING
            cam_y += (target_cam_y - cam_y) * CAMERA_SMOOTHING

        SCREEN.fill((20, 20, 20))
        game_view_rect = pygame.Rect(UI_WIDTH, 0, GAME_WIDTH, SCREEN_HEIGHT)
        SCREEN.set_clip(game_view_rect)
        SCREEN.blit(TRACK, (0 - cam_x, 0 - cam_y))
        
        for i, car_group in enumerate(cars):
            car = car_group.sprite
            if car.alive:
                draw_pos = (car.rect.x - cam_x, car.rect.y - cam_y)
                SCREEN.blit(car.image, draw_pos)
                if car == leader:
                    for r_data in car.radars:
                        if len(r_data) >= 3:
                            end_pt = r_data[2]
                            start_pt = car.rect.center
                            adj_start = (start_pt[0] - cam_x, start_pt[1] - cam_y)
                            adj_end = (end_pt[0] - cam_x, end_pt[1] - cam_y)
                            pygame.draw.line(SCREEN, (255, 255, 255), adj_start, adj_end, 1)
                            pygame.draw.circle(SCREEN, (0, 255, 0), (int(adj_end[0]), int(adj_end[1])), 3)

        SCREEN.set_clip(None)
        pygame.draw.rect(SCREEN, COLOR_UI_BG, (0, 0, UI_WIDTH, SCREEN_HEIGHT))
        pygame.draw.line(SCREEN, (50, 50, 50), (UI_WIDTH, 0), (UI_WIDTH, SCREEN_HEIGHT), 2)

        draw_f1_leaderboard(SCREEN, cars)
        if leader: draw_chase_cam(SCREEN, leader)
        if show_telemetry: draw_telemetry_panel(SCREEN, cars)
        if show_network and leader_genome:
            draw_neural_network(SCREEN, leader_genome, config, leader, leader_inputs, leader_outputs)
        draw_ui_buttons(SCREEN)

        for i, car_group in enumerate(cars):
            car = car_group.sprite
            genome = genomes[i][1]
            if car.lap_completed and car.lap_times:
                last_lap = car.lap_times[-1]      
                lap_seconds = last_lap / 1000.0
                genome.fitness += 1000 
                time_bonus = 6000 / max(1, lap_seconds) * 10 
                genome.fitness += time_bonus
                car.lap_completed = False

        pygame.display.update()
        clock.tick(60)

        if all(not car_group.sprite.alive for car_group in cars): run = False

    if quit_flag: sys.exit(0)

def run(config_path):
    try:
        config = neat.config.Config(neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet, neat.DefaultStagnation, config_path)
        pop = neat.Population(config)
        pop.add_reporter(neat.StdOutReporter(True))
        stats = neat.StatisticsReporter()
        pop.add_reporter(stats)
        pop.add_reporter(neat.Checkpointer(5))
        pop.run(eval_genomes, 5000)
    except KeyboardInterrupt:
        print("Evolution stopped by user.")
        pygame.quit()
        sys.exit()
    except Exception as e:
        print(f"CRASH DETECTED: {e}")
        traceback.print_exc()
        SCREEN.fill((50, 0, 0))
        err_surf = FONT_ERROR.render("GAME CRASHED!", True, (255, 255, 255))
        msg_surf = FONT_MAIN.render(str(e), True, (255, 200, 200))
        hint_surf = FONT_MAIN.render("Check console for full error details.", True, (200, 200, 200))
        SCREEN.blit(err_surf, (50, 50))
        SCREEN.blit(msg_surf, (50, 100))
        SCREEN.blit(hint_surf, (50, 150))
        pygame.display.update()
        time.sleep(10)
        pygame.quit()
        sys.exit()

if __name__ == '__main__':
    local_dir = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'config.txt')
    print("Loading config from:", config_path)
    run(config_path)