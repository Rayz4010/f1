import pygame
import os
import math
import neat
import threading
import time

pygame.init()

# Get screen info for fullscreen
info = pygame.display.Info()
SCREEN_WIDTH = info.current_w
SCREEN_HEIGHT = info.current_h
SCREEN = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)

# --- LAYOUT CONFIGURATION ---
# Allocate 75% width for the track, 25% for the UI/Leaderboard
UI_PERCENTAGE = 0.25
UI_WIDTH = int(SCREEN_WIDTH * UI_PERCENTAGE)
GAME_WIDTH = SCREEN_WIDTH - UI_WIDTH
TRACK_X_OFFSET = UI_WIDTH  # Track starts after the UI panel (Left side UI, Right side Track)

# Load Assets
try:
    TRACK = pygame.image.load(os.path.join("assets", "track.png"))
except FileNotFoundError:
    print("Error: assets/track.png not found. Please ensure the file exists.")
    pygame.quit()
    exit()

original_width, original_height = TRACK.get_width(), TRACK.get_height()

# Scale Track to fit the GAME_WIDTH only
TRACK = pygame.transform.scale(TRACK, (GAME_WIDTH, SCREEN_HEIGHT))

scale_x = GAME_WIDTH / original_width
scale_y = SCREEN_HEIGHT / original_height
scale = min(scale_x, scale_y)

# F1 Style Fonts
try:
    FONT_MAIN = pygame.font.SysFont("Consolas", int(18 * scale), bold=True)
    FONT_HEADER = pygame.font.SysFont("Arial", int(20 * scale), bold=True)
except:
    FONT_MAIN = pygame.font.SysFont(None, int(22 * scale))
    FONT_HEADER = pygame.font.SysFont(None, int(24 * scale))

quit_flag = False
manual_reset = False  # Flag to trigger next generation manually
show_telemetry = False  # Default to hidden, toggle with 'I'

# --- BUTTONS CONFIGURATION ---
BUTTON_PADDING = int(20 * scale)
BUTTON_WIDTH = int(140 * scale)
BUTTON_HEIGHT = int(48 * scale)

# Exit Button (Top Right)
EXIT_BUTTON_RECT = pygame.Rect(
    SCREEN_WIDTH - BUTTON_WIDTH - BUTTON_PADDING, 
    BUTTON_PADDING, 
    BUTTON_WIDTH, 
    BUTTON_HEIGHT
)

# Reset Button (Left of Exit Button)
RESET_BUTTON_RECT = pygame.Rect(
    SCREEN_WIDTH - (BUTTON_WIDTH * 2) - (BUTTON_PADDING * 2), 
    BUTTON_PADDING, 
    BUTTON_WIDTH, 
    BUTTON_HEIGHT
)

# Colors
EXIT_BUTTON_COLOR = (200, 0, 0)
RESET_BUTTON_COLOR = (255, 140, 0) # Dark Orange
EXIT_BUTTON_BORDER_COLOR = (255, 255, 255)
BUTTON_TEXT_COLOR = (255, 255, 255)

# F1 Theme Colors
COLOR_UI_BG = (30, 30, 30)     
COLOR_BG_PANEL = (20, 20, 20, 200) 
COLOR_TEXT_WHITE = (255, 255, 255)
COLOR_TEXT_GREY = (150, 150, 150)
COLOR_PURPLE = (218, 112, 214) 
COLOR_GREEN = (0, 200, 0)      
COLOR_RED = (200, 50, 50)
COLOR_BLUE = (0, 191, 255)

# Global best lap tracker
BEST_OVERALL_LAP = float('inf')

def format_time(ms):
    """Converts milliseconds to M:SS.mmm format"""
    minutes = int(ms // 60000)
    seconds = int((ms % 60000) // 1000)
    milliseconds = int(ms % 1000)
    return f"{minutes}:{seconds:02}.{milliseconds:03}"

def draw_ui_buttons(surface):
    """Draws both Exit and Reset buttons"""
    # 1. Exit Button
    pygame.draw.rect(surface, EXIT_BUTTON_COLOR, EXIT_BUTTON_RECT)
    pygame.draw.rect(surface, EXIT_BUTTON_BORDER_COLOR, EXIT_BUTTON_RECT, max(1, int(2 * scale)))
    label_exit = FONT_MAIN.render("Exit", True, BUTTON_TEXT_COLOR)
    label_rect_exit = label_exit.get_rect(center=EXIT_BUTTON_RECT.center)
    surface.blit(label_exit, label_rect_exit)

    # 2. Reset Gen Button
    pygame.draw.rect(surface, RESET_BUTTON_COLOR, RESET_BUTTON_RECT)
    pygame.draw.rect(surface, EXIT_BUTTON_BORDER_COLOR, RESET_BUTTON_RECT, max(1, int(2 * scale)))
    label_reset = FONT_MAIN.render("Reset Gen", True, BUTTON_TEXT_COLOR)
    label_rect_reset = label_reset.get_rect(center=RESET_BUTTON_RECT.center)
    surface.blit(label_reset, label_rect_reset)

def _monitor_buttons_thread():
    """Thread to handle button clicks (Exit and Reset)"""
    global manual_reset, quit_flag
    pressed = False
    while True:
        if quit_flag:
            break
        mouse_pressed = pygame.mouse.get_pressed(num_buttons=3)
        if mouse_pressed[0]:
            if not pressed:
                pressed = True
                mx, my = pygame.mouse.get_pos()
                
                # Check Exit
                if EXIT_BUTTON_RECT.collidepoint(mx, my):
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                
                # Check Reset
                if RESET_BUTTON_RECT.collidepoint(mx, my):
                    manual_reset = True
        else:
            pressed = False
        time.sleep(0.05)

threading.Thread(target=_monitor_buttons_thread, daemon=True).start()

class Car(pygame.sprite.Sprite):
    def __init__(self, car_id):
        super().__init__()
        self.car_id = car_id
        try:
            self.original_image = pygame.image.load(os.path.join("assets", "car.png"))
        except FileNotFoundError:
             # Fallback if car.png is missing: simple red rect
            self.original_image = pygame.Surface((30, 50))
            self.original_image.fill((255, 0, 0))

        car_scale = scale * 0.2
        self.original_image = pygame.transform.scale(self.original_image, (int(self.original_image.get_width() * car_scale), int(self.original_image.get_height() * car_scale)))
        self.image = self.original_image
        # Adjust start position: Shift to the right by TRACK_X_OFFSET
        self.start_pos = (TRACK_X_OFFSET + 490 * scale_x, 820 * scale_y)
        self.rect = self.image.get_rect(center=self.start_pos)
        self.vel_vector = pygame.math.Vector2(0.8, 0)
        self.angle = 0
        self.rotation_vel = 5
        self.direction = 0
        self.alive = True
        self.radars = []
        self.lap_started = False
        self.lap_completed = False
        self.current_lap_time = 0
        self.lap_start_time = 0
        self.lap_times = []
        self.personal_best = float('inf')
        self.speed = 6
        self.max_speed = 20 
        self.steer_left = 0
        self.steer_right = 0
        self.brake = 0
        self.accelerator = 0
        self.scale = scale
        self.last_pos = pygame.math.Vector2(self.rect.center)
        self.stuck_frames = 0
        self.steer = 0.0   
        self.distance_travelled = 0.0


    def update(self):
        self.radars.clear()
        self.drive()
        self.check_lap()
        self.rotate()
        for radar_angle in (-60, -30, 0, 30, 60):
            self.radar(radar_angle)
        self.collision()
        
        # --- NEW: Anti-Spinning Logic ---
        # If the car is moving fast but turning excessively without making progress
        if self.speed > 2 and abs(self.steer) > 0.9:
            # You can add a counter here, if they do this for 50 frames, kill them
            pass

        # --- Anti-stuck based on actual movement ---
        current_pos = pygame.math.Vector2(self.rect.center)
        moved_dist = (current_pos - self.last_pos).length()

        if moved_dist < 1.0:        # basically not moving
            self.stuck_frames += 1
        else:
            self.stuck_frames = 0

        self.last_pos = current_pos

        # If stuck for more than 3 seconds at 60 FPS, kill the car
        if self.stuck_frames > 180:
            self.alive = False
        # -------------------------------------------

        self.data()


    def drive(self):
        # Apply throttle / brake
        self.speed += (self.accelerator - self.brake) * 0.1

        # Simple friction
        self.speed *= 0.99

        # Clamp
        self.speed = max(0, min(self.max_speed, self.speed))

        self.rect.center += self.vel_vector * self.speed
        
        # Track progress
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
                
                # Small reward: higher potential top speed + a little shove
                self.max_speed = min(self.max_speed + 2, 30)   # don’t go crazy, cap at 30
                self.speed = min(self.speed + 2, self.max_speed)

                self.lap_started = False
                self.lap_completed = False
                self.lap_start_time = 0
                self.current_lap_time = 0


    def collision(self):
        length = 40 * self.scale
        collision_point_right = [int(self.rect.center[0] + math.cos(math.radians(self.angle + 18)) * length),
                                 int(self.rect.center[1] - math.sin(math.radians(self.angle + 18)) * length)]
        collision_point_left = [int(self.rect.center[0] + math.cos(math.radians(self.angle - 18)) * length),
                                int(self.rect.center[1] - math.sin(math.radians(self.angle - 18)) * length)]

        # Check collisions: Using screen coordinates, this works naturally with the shifted track
        if SCREEN.get_at(collision_point_right) == pygame.Color(2, 105, 31, 255) \
                or SCREEN.get_at(collision_point_left) == pygame.Color(2, 105, 31, 255):
            self.alive = False

    def rotate(self):
        if self.direction == 1:
            self.angle -= self.rotation_vel
            self.vel_vector.rotate_ip(self.rotation_vel)
        if self.direction == -1:
            self.angle += self.rotation_vel
            self.vel_vector.rotate_ip(-self.rotation_vel)

        self.image = pygame.transform.rotozoom(self.original_image, self.angle, 1)
        self.rect = self.image.get_rect(center=self.rect.center)

    def radar(self, radar_angle):
        length = 0
        x = int(self.rect.center[0])
        y = int(self.rect.center[1])

        while length < 300 * self.scale:
            # Important: Limit radar check to TRACK Area (Right Side)
            if not (TRACK_X_OFFSET <= x < SCREEN_WIDTH and 0 <= y < SCREEN_HEIGHT):
                break
            
            try:
                if SCREEN.get_at((x, y)) == pygame.Color(2, 105, 31, 255):
                    break
            except IndexError:
                break

            length += 1
            x = int(self.rect.center[0] + math.cos(math.radians(self.angle + radar_angle)) * length)
            y = int(self.rect.center[1] - math.sin(math.radians(self.angle + radar_angle)) * length)

        pygame.draw.line(SCREEN, (255, 255, 255, 255), self.rect.center, (x, y), 1)
        pygame.draw.circle(SCREEN, (0, 255, 0, 0), (x, y), 3)

        dist = int(math.sqrt(math.pow(self.rect.center[0] - x, 2)
                             + math.pow(self.rect.center[1] - y, 2)))
        self.radars.append([radar_angle, dist])

    def data(self):
        input = [0, 0, 0, 0, 0]
        for i, radar in enumerate(self.radars):
            input[i] = int(radar[1])
        return input

def draw_f1_leaderboard(screen, cars):
    start_x = 0
    start_y = 0
    row_height = 40 * scale

    # 1. Filter: Create a list of ONLY alive cars
    #    'cars' is a list of sprite groups, so we access .sprite to get the car object
    active_cars = [group.sprite for group in cars if group.sprite.alive]

    # 2. Sort: Order them by distance travelled (Highest first)
    #    This makes "POS 1" actually the car that is winning
    active_cars.sort(key=lambda x: x.distance_travelled, reverse=True)

    # Header
    header_rect = pygame.Rect(start_x, start_y, UI_WIDTH, row_height)
    pygame.draw.rect(screen, (255, 0, 0), header_rect)
    header_text = FONT_HEADER.render("POS  DRIVER             TIME", True, COLOR_TEXT_WHITE)
    screen.blit(header_text, (start_x + 10, start_y + 10))

    # 3. Draw only the active cars
    for i, car in enumerate(active_cars):
        y_pos = start_y + row_height + (i * row_height)

        text_color = COLOR_TEXT_WHITE
        time_text = ""

        # Logic for Time Display
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

        # Draw Separator Line
        pygame.draw.line(screen, (50, 50, 50), (start_x, y_pos), (UI_WIDTH, y_pos), 1)

        # Position (1, 2, 3...)
        pos_str = f"{i + 1}"
        pos_render = FONT_MAIN.render(pos_str, True, text_color)
        screen.blit(pos_render, (start_x + 10, y_pos + 10))

        # Driver Name (Car ID)
        driver_str = f"CAR {car.car_id}"
        driver_render = FONT_MAIN.render(driver_str, True, text_color)
        screen.blit(driver_render, (start_x + 50, y_pos + 10))

        # Time
        time_render = FONT_MAIN.render(time_text, True, text_color)
        time_rect = time_render.get_rect(right=UI_WIDTH - 20, top=y_pos + 10)
        screen.blit(time_render, time_rect)

def draw_telemetry_panel(screen, cars):
    panel_width = 230 * scale
    row_height = 30 * scale
    header_height = 30 * scale
    
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
        
        telemetry_x = start_x + 50 * scale 
        bar_max_width = 35 * scale
        bar_height = 6 * scale
        
        if car.alive:
            # Accelerator
            accel_val = max(0, min(1, car.accelerator))
            accel_width = accel_val * bar_max_width
            pygame.draw.rect(screen, (0, 80, 0), (telemetry_x, y_pos + 8 * scale, bar_max_width, bar_height), 1)
            pygame.draw.rect(screen, COLOR_GREEN, (telemetry_x, y_pos + 8 * scale, accel_width, bar_height))

            # Brake
            brake_x = telemetry_x + bar_max_width + 4 * scale
            brake_val = max(0, min(1, car.brake))
            brake_width = brake_val * bar_max_width
            pygame.draw.rect(screen, (80, 0, 0), (brake_x, y_pos + 8 * scale, bar_max_width, bar_height), 1)
            pygame.draw.rect(screen, COLOR_RED, (brake_x, y_pos + 8 * scale, brake_width, bar_height))

            # Steering
            steer_y = y_pos + 18 * scale
            total_steer_width = (bar_max_width * 2) + 4 * scale
            center_x = telemetry_x + (total_steer_width / 2)

            pygame.draw.line(screen, (100,100,100), (telemetry_x, steer_y + bar_height/2), (telemetry_x + total_steer_width, steer_y + bar_height/2), 1)
            pygame.draw.line(screen, (200,200,200), (center_x, steer_y), (center_x, steer_y + bar_height), 1)

            steer = max(-1, min(1, car.steer))
            steer_pixels = steer * (total_steer_width / 2)

            if steer_pixels > 0:    # turning right
                pygame.draw.rect(screen, COLOR_BLUE, (center_x, steer_y, steer_pixels, bar_height))
            else:                   # turning left
                pygame.draw.rect(screen, COLOR_BLUE, (center_x + steer_pixels, steer_y, abs(steer_pixels), bar_height))
        else:
            pygame.draw.rect(screen, COLOR_TEXT_GREY, (telemetry_x, y_pos + 8 * scale, bar_max_width, bar_height), 1)
            pygame.draw.rect(screen, COLOR_TEXT_GREY, (telemetry_x + bar_max_width + 4 * scale, y_pos + 8 * scale, bar_max_width, bar_height), 1)
            pygame.draw.rect(screen, COLOR_TEXT_GREY, (telemetry_x, y_pos + 18 * scale, (bar_max_width * 2) + 4 * scale, bar_height), 1)


def eval_genomes(genomes, config):
    global quit_flag, BEST_OVERALL_LAP, show_telemetry, manual_reset
    
    # IMPORTANT: Reset flag at start of each generation
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
    run = True
    
    while run and (pygame.time.get_ticks() - start_time) < 360000:
        
        # --- RESET CHECK ---
        if manual_reset:
            run = False
        # -------------------

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_flag = True
                run = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_i:
                    show_telemetry = not show_telemetry

        # 1. Draw Track & UI BG
        SCREEN.blit(TRACK, (TRACK_X_OFFSET, 0))
        pygame.draw.rect(SCREEN, COLOR_UI_BG, (0, 0, UI_WIDTH, SCREEN_HEIGHT))

        # 2. Update Cars
        for i, car_group in enumerate(cars):
            car = car_group.sprite
            if not car.alive:
                continue

            raw = nets[i].activate(car.data())
            while len(raw) < 4:
                raw = list(raw) + [0.0]

            car.steer_left  = raw[0]
            car.steer_right = raw[1]
            steer = car.steer_right - car.steer_left

            if abs(steer) < 0.2:
                steer = 0.0

            car.steer = max(-1.0, min(1.0, steer))

            car.brake       = (raw[2] + 1) / 2.0
            car.accelerator = (raw[3] + 1) / 2.0

            car.brake       = max(0.0, min(1.0, car.brake))
            car.accelerator = max(0.0, min(1.0, car.accelerator))

            if car.steer_left > 0.7:
                car.direction = 1
            elif car.steer_right > 0.7:
                car.direction = -1
            else:
                car.direction = 0

            car.update()

            # 1. Reward distance heavily so "almost finishing" is good
            genomes[i][1].fitness += car.speed * 0.1 
            
            # 2. Small constant reward for staying alive (encourages not crashing immediately)
            genomes[i][1].fitness += 0.05

            car_group.draw(SCREEN)
            
            

        # Reward Logic
        for i, car_group in enumerate(cars):
            car = car_group.sprite
            genome = genomes[i][1]

            if car.lap_completed and car.lap_times:
                last_lap = car.lap_times[-1]      
                lap_seconds = last_lap / 1000.0

                # OLD BONUS: 5000 (Too high, creates "God" cars)
                # NEW BONUS: 1000 + speed incentive
                
                # Give a flat bonus for finishing + bonus for speed
                lap_bonus = 1000.0 
                
                # Extra bonus for doing it fast
                if lap_seconds < 30: # Arbitrary "fast" time
                    lap_bonus += 500 

                genome.fitness += lap_bonus

                # Instead of killing the car, let it keep driving to learn consistency!
                # car.alive = False 
                
                # Reset lap flags to let it try for a second lap (Consistency training)
                car.lap_completed = False
                # Optionally increase speed cap slightly to let it push limits
                car.max_speed = min(car.max_speed + 1, 25)
                
                
        # 3. Draw HUD Overlays
        draw_f1_leaderboard(SCREEN, cars)
        if show_telemetry:
            draw_telemetry_panel(SCREEN, cars)
        
        draw_ui_buttons(SCREEN) # Draws both Exit and Reset

        pygame.display.update()
        clock.tick(60)

        if all(not car_group.sprite.alive for car_group in cars):
            run = False

    if quit_flag:
        raise KeyboardInterrupt

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

    try:
        pop.run(eval_genomes, 500)
    except KeyboardInterrupt:
        print("Evolution stopped by user.")

if __name__ == '__main__':
    local_dir = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'config.txt')
    print("Loading config from:", config_path)
    run(config_path)