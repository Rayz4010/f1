import pygame
import os
import math
import sys
import threading
import time

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
ZOOM_FACTOR = 2.5  # How much to zoom in (Like the video)
CAMERA_SMOOTHING = 0.1 # Lower = Smoother camera, Higher = Snappier

# Load Assets
try:
    TRACK = pygame.image.load(os.path.join("assets", "track.png")).convert()
except FileNotFoundError:
    print("Error: assets/track.png not found. Please ensure the file exists.")
    pygame.quit()
    exit()

original_width, original_height = TRACK.get_width(), TRACK.get_height()

# --- SCALE CALCULATION ---
# We calculate the scale to fit the screen, then multiply by ZOOM_FACTOR
base_scale_x = GAME_WIDTH / original_width
base_scale_y = SCREEN_HEIGHT / original_height
scale = min(base_scale_x, base_scale_y) * ZOOM_FACTOR

# Scale the TRACK surface to the new zoomed size
# The track is now likely LARGER than the screen
scaled_width = int(original_width * scale)
scaled_height = int(original_height * scale)
TRACK = pygame.transform.scale(TRACK, (scaled_width, scaled_height))

# Fonts
try:
    FONT_MAIN = pygame.font.SysFont("Consolas", int(18), bold=True)
    FONT_HEADER = pygame.font.SysFont("Arial", int(20), bold=True)
except:
    FONT_MAIN = pygame.font.SysFont(None, 22)
    FONT_HEADER = pygame.font.SysFont(None, 24)

quit_flag = False
manual_reset = False
show_telemetry = False

# BUTTONS CONFIGURATION
BUTTON_PADDING = 20
BUTTON_WIDTH = 140
BUTTON_HEIGHT = 48

EXIT_BUTTON_RECT = pygame.Rect(
    SCREEN_WIDTH - BUTTON_WIDTH - BUTTON_PADDING, 
    BUTTON_PADDING, 
    BUTTON_WIDTH, 
    BUTTON_HEIGHT
)

RESET_BUTTON_RECT = pygame.Rect(
    SCREEN_WIDTH - (BUTTON_WIDTH * 2) - (BUTTON_PADDING * 2), 
    BUTTON_PADDING, 
    BUTTON_WIDTH, 
    BUTTON_HEIGHT
)

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

def draw_ui_buttons(surface):
    pygame.draw.rect(surface, EXIT_BUTTON_COLOR, EXIT_BUTTON_RECT)
    pygame.draw.rect(surface, EXIT_BUTTON_BORDER_COLOR, EXIT_BUTTON_RECT, 2)
    label_exit = FONT_MAIN.render("Exit", True, BUTTON_TEXT_COLOR)
    label_rect_exit = label_exit.get_rect(center=EXIT_BUTTON_RECT.center)
    surface.blit(label_exit, label_rect_exit)

    pygame.draw.rect(surface, RESET_BUTTON_COLOR, RESET_BUTTON_RECT)
    pygame.draw.rect(surface, EXIT_BUTTON_BORDER_COLOR, RESET_BUTTON_RECT, 2)
    label_reset = FONT_MAIN.render("New Gen", True, BUTTON_TEXT_COLOR)
    label_rect_reset = label_reset.get_rect(center=RESET_BUTTON_RECT.center)
    surface.blit(label_reset, label_rect_reset)

def _monitor_buttons_thread():
    global manual_reset, quit_flag
    pressed = False
    while True:
        if quit_flag:
            break
        try:
            if not pygame.get_init():
                break
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
        except:
            break
        time.sleep(0.05)

threading.Thread(target=_monitor_buttons_thread, daemon=True).start()

class Car(pygame.sprite.Sprite):
    def __init__(self, car_id):
        super().__init__()
        self.car_id = car_id
        try:
            self.original_image = pygame.image.load(os.path.join("assets", "car.png")).convert_alpha()
        except FileNotFoundError:
            self.original_image = pygame.Surface((30, 50))
            self.original_image.fill((255, 0, 0))

        # Scale car relative to the new Zoom
        car_scale = scale * 0.2
        self.original_image = pygame.transform.scale(self.original_image, (int(self.original_image.get_width() * car_scale), int(self.original_image.get_height() * car_scale)))
        self.image = self.original_image
        
        # Start Position (Scaled to the new larger track)
        # Note: We assume the track starts near the same relative spot.
        # We multiply the original relative position by the new scale.
        self.start_pos = (490 * (scaled_width / original_width), 820 * (scaled_height / original_height))
        
        self.rect = self.image.get_rect(center=self.start_pos)
        self.vel_vector = pygame.math.Vector2(0.8, 0)
        self.angle = 0
        
        # Increase speeds slightly to match the larger world size
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
        self.max_speed = 35 * (ZOOM_FACTOR * 0.8) # Adjust max speed for zoom
        
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
        
        self.STEER_SMOOTHING = 0.1  
        self.ACCEL_SMOOTHING = 0.1

    def update(self, is_leader=False):
        self.time_alive += 1
        
        if self.time_alive < 30:
            self.target_accel = 1.0
            self.target_brake = 0.0

        self.smooth_controls()
        self.radars.clear()
        self.drive()
        self.check_lap()
        self.rotate()
        
        if is_leader:
            self.image.set_alpha(255) 
        else:
            self.image.set_alpha(100)

        for radar_angle in (-60, -30, 0, 30, 60):
            self.radar(radar_angle, draw=is_leader)
            
        self.collision()
        
        if self.time_alive > 240 and self.speed < 0.5:
            self.alive = False

        if abs(self.current_steer) > 0.8 and self.speed < 3.0 and self.time_alive > 120:
            self.alive = False
            
        current_pos = pygame.math.Vector2(self.rect.center)
        moved_dist = (current_pos - self.last_pos).length()

        if moved_dist < 0.5: 
            self.stuck_frames += 1
        else:
            self.stuck_frames = 0
        self.last_pos = current_pos

        if self.stuck_frames > 90:
            self.alive = False

        self.data()

    def smooth_controls(self):
        self.current_steer += (self.target_steer - self.current_steer) * self.STEER_SMOOTHING
        self.current_accel += (self.target_accel - self.current_accel) * self.ACCEL_SMOOTHING
        self.current_brake += (self.target_brake - self.current_brake) * self.ACCEL_SMOOTHING

    def drive(self):
        torque = 0.5 
        if self.speed > 15: # adjusted for zoom speed
            torque = 0.15 

        self.speed += (self.current_accel * torque)
        
        brake_power = 0.3
        if self.speed < 5:
            brake_power = 0.05
            
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
                
                if final_time < self.personal_best:
                    self.personal_best = final_time
                if final_time < BEST_OVERALL_LAP:
                    BEST_OVERALL_LAP = final_time
                
                # Incentive
                self.max_speed = min(self.max_speed + 5, 100) 

                self.lap_started = False
                self.lap_completed = False
                self.lap_start_time = 0
                self.current_lap_time = 0

    def collision(self):
        # IMPORTANT: With a scrolling camera, we CANNOT check SCREEN.get_at()
        # because the car might be "off screen" or the screen pixels might represent the wrong place.
        # We must check the TRACK surface directly.
        
        length = 40 * self.scale
        
        # Calculate points
        right_pt = [int(self.rect.center[0] + math.cos(math.radians(self.angle + 18)) * length),
                    int(self.rect.center[1] - math.sin(math.radians(self.angle + 18)) * length)]
        left_pt  = [int(self.rect.center[0] + math.cos(math.radians(self.angle - 18)) * length),
                    int(self.rect.center[1] - math.sin(math.radians(self.angle - 18)) * length)]

        # Check bounds first to prevent crash if car goes out of the huge track map
        max_w, max_h = TRACK.get_width(), TRACK.get_height()
        
        # Helper to check color
        def is_collision(pt):
            if pt[0] < 0 or pt[0] >= max_w or pt[1] < 0 or pt[1] >= max_h:
                return True # Out of bounds is collision
            try:
                # Check against TRACK surface, not SCREEN
                return TRACK.get_at(pt) == pygame.Color(2, 105, 31, 255)
            except:
                return True

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
            if x < 0 or x >= max_w or y < 0 or y >= max_h:
                break
            try:
                # Check against TRACK
                if TRACK.get_at((x, y)) == pygame.Color(2, 105, 31, 255):
                    break
            except IndexError:
                break
            length += 1
            x = int(self.rect.center[0] + math.cos(math.radians(self.angle + radar_angle)) * length)
            y = int(self.rect.center[1] - math.sin(math.radians(self.angle + radar_angle)) * length)

        # Store visual points for drawing later (relative to camera)
        # We store World Coordinates here
        dist = int(math.sqrt(math.pow(self.rect.center[0] - x, 2)
                             + math.pow(self.rect.center[1] - y, 2)))
        self.radars.append([radar_angle, dist, (x, y)])

    def data(self):
        input = [0, 0, 0, 0, 0]
        for i, radar in enumerate(self.radars):
            input[i] = int(radar[1]) / (300.0 * self.scale) # Normalize
        return input

def draw_f1_leaderboard(screen, cars):
    start_x = 0
    start_y = 0
    row_height = 40 
    active_cars = [group.sprite for group in cars if group.sprite.alive]
    active_cars.sort(key=lambda x: x.distance_travelled, reverse=True)

    header_rect = pygame.Rect(start_x, start_y, UI_WIDTH, row_height)
    pygame.draw.rect(screen, (255, 0, 0), header_rect)
    header_text = FONT_HEADER.render("POS  DRIVER             TIME", True, COLOR_TEXT_WHITE)
    screen.blit(header_text, (start_x + 10, start_y + 10))

    for i, car in enumerate(active_cars):
        y_pos = start_y + row_height + (i * row_height)
        text_color = COLOR_TEXT_WHITE
        time_text = ""

        if len(car.lap_times) > 0:
            last_lap = car.lap_times[-1]
            time_text = format_time(last_lap)
            if last_lap == BEST_OVERALL_LAP:
                text_color = COLOR_PURPLE
            elif last_lap == car.personal_best:
                text_color = COLOR_GREEN
        else:
            time_text = format_time(car.current_lap_time)
            text_color = (255, 255, 200)

        pygame.draw.line(screen, (50, 50, 50), (start_x, y_pos), (UI_WIDTH, y_pos), 1)
        screen.blit(FONT_MAIN.render(f"{i + 1}", True, text_color), (start_x + 10, y_pos + 10))
        screen.blit(FONT_MAIN.render(f"CAR {car.car_id}", True, text_color), (start_x + 50, y_pos + 10))
        time_render = FONT_MAIN.render(time_text, True, text_color)
        time_rect = time_render.get_rect(right=UI_WIDTH - 20, top=y_pos + 10)
        screen.blit(time_render, time_rect)

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

def eval_genomes(genomes, config):
    global quit_flag, BEST_OVERALL_LAP, show_telemetry, manual_reset
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
    
    # Camera variables
    cam_x = 0
    cam_y = 0
    
    run = True
    
    while run:
        if manual_reset:
            run = False
        
        if (pygame.time.get_ticks() - start_time) > 600000:
            run = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_flag = True
                run = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_i:
                    show_telemetry = not show_telemetry

        # 1. Update Cars
        alive_cars = [c.sprite for c in cars if c.sprite.alive]
        leader = None
        if alive_cars:
            leader = max(alive_cars, key=lambda c: c.distance_travelled)

        # 2. Camera Update (Smooth follow)
        if leader:
            # Target is to center the leader in the GAME AREA (Right side of screen)
            # The game area starts at UI_WIDTH and ends at SCREEN_WIDTH
            game_center_x = UI_WIDTH + (GAME_WIDTH / 2)
            game_center_y = SCREEN_HEIGHT / 2
            
            target_cam_x = leader.rect.centerx - game_center_x
            target_cam_y = leader.rect.centery - game_center_y
            
            # Linear Interpolation (Lerp) for smoothness
            cam_x += (target_cam_x - cam_x) * CAMERA_SMOOTHING
            cam_y += (target_cam_y - cam_y) * CAMERA_SMOOTHING
        
        # Clamp camera so we don't see too much black void (Optional)
        # For now, we allow free movement to ensure leader is always centered

        for i, car_group in enumerate(cars):
            car = car_group.sprite
            if not car.alive:
                continue

            # Auto Launch Force
            if car.time_alive < 30:
                 raw = [0, 0, 0, 0]
            else:
                 raw = nets[i].activate(car.data())
                 while len(raw) < 4:
                     raw = list(raw) + [0.0]

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

            genomes[i][1].fitness += car.speed * 0.1 
            genomes[i][1].fitness -= abs(car.target_steer - car.current_steer) * 1.5

        # 3. DRAWING (SCROLLING WORLD)
        
        # Clear screen
        SCREEN.fill((20, 20, 20)) # Dark Grey background
        
        # Define the visible Game Area Rect
        game_view_rect = pygame.Rect(UI_WIDTH, 0, GAME_WIDTH, SCREEN_HEIGHT)
        
        # Set clipping so drawing doesn't spill into the UI panel
        SCREEN.set_clip(game_view_rect)
        
        # Draw Track (Shifted by camera)
        SCREEN.blit(TRACK, (0 - cam_x, 0 - cam_y))
        
        # Draw Cars (Shifted by camera)
        for i, car_group in enumerate(cars):
            car = car_group.sprite
            if car.alive:
                # Manual drawing to apply offset
                # car.image is the rotated sprite
                # car.rect is the position in WORLD coordinates
                
                draw_pos = (car.rect.x - cam_x, car.rect.y - cam_y)
                SCREEN.blit(car.image, draw_pos)
                
                # Draw Leader Radar (Shifted)
                if car == leader:
                    for r_data in car.radars:
                        # r_data = [angle, dist, (world_x, world_y)]
                        # We need the 3rd element (endpoint) from radar()
                        if len(r_data) >= 3:
                            end_pt = r_data[2]
                            start_pt = car.rect.center
                            
                            adj_start = (start_pt[0] - cam_x, start_pt[1] - cam_y)
                            adj_end = (end_pt[0] - cam_x, end_pt[1] - cam_y)
                            
                            pygame.draw.line(SCREEN, (255, 255, 255), adj_start, adj_end, 1)
                            pygame.draw.circle(SCREEN, (0, 255, 0), (int(adj_end[0]), int(adj_end[1])), 3)

        # Reset clipping to draw UI
        SCREEN.set_clip(None)
        
        # Draw UI Background (Left Panel)
        pygame.draw.rect(SCREEN, COLOR_UI_BG, (0, 0, UI_WIDTH, SCREEN_HEIGHT))
        pygame.draw.line(SCREEN, (50, 50, 50), (UI_WIDTH, 0), (UI_WIDTH, SCREEN_HEIGHT), 2)

        # Draw Overlays
        draw_f1_leaderboard(SCREEN, cars)
        if show_telemetry:
            draw_telemetry_panel(SCREEN, cars)
        draw_ui_buttons(SCREEN)

        # Check Laps
        for i, car_group in enumerate(cars):
            car = car_group.sprite
            genome = genomes[i][1]
            if car.lap_completed and car.lap_times:
                last_lap = car.lap_times[-1]      
                lap_seconds = last_lap / 1000.0
                lap_bonus = 2000.0 
                if lap_seconds < 25: lap_bonus += 1000 
                genome.fitness += lap_bonus
                car.lap_completed = False

        pygame.display.update()
        clock.tick(60)

        if all(not car_group.sprite.alive for car_group in cars):
            run = False

    if quit_flag:
        sys.exit(0)

def run(config_path):
    config = neat.config.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        config_path
    )

    pop = neat.Population(config)
    pop.add_reporter(neat.StdOutReporter(True))
    stats = neat.StatisticsReporter()
    pop.add_reporter(stats)
    pop.add_reporter(neat.Checkpointer(5))

    try:
        pop.run(eval_genomes, 5000)
    except KeyboardInterrupt:
        print("Evolution stopped by user.")
        pygame.quit()
        sys.exit()

if __name__ == '__main__':
    local_dir = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'config.txt')
    print("Loading config from:", config_path)
    run(config_path)