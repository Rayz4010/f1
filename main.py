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

TRACK = pygame.image.load(os.path.join("assets", "track.png"))
original_width, original_height = TRACK.get_width(), TRACK.get_height()

# Scale Track to fit the GAME_WIDTH only
TRACK = pygame.transform.scale(TRACK, (GAME_WIDTH, SCREEN_HEIGHT))

scale_x = GAME_WIDTH / original_width
scale_y = SCREEN_HEIGHT / original_height
scale = min(scale_x, scale_y)

# F1 Style Fonts
try:
    FONT_MAIN = pygame.font.SysFont("Consolas", int(18 * scale), bold=True) # Slightly smaller for more info
    FONT_HEADER = pygame.font.SysFont("Arial", int(20 * scale), bold=True)
except:
    FONT_MAIN = pygame.font.SysFont(None, int(22 * scale))
    FONT_HEADER = pygame.font.SysFont(None, int(24 * scale))

quit_flag = False
show_telemetry = False  # Default to hidden, toggle with 'I'

# Exit button setup - Positioned at the top right of the screen
BUTTON_PADDING = int(20 * scale)
BUTTON_WIDTH = int(140 * scale)
BUTTON_HEIGHT = int(48 * scale)
# Top Right positioning
EXIT_BUTTON_RECT = pygame.Rect(
    SCREEN_WIDTH - BUTTON_WIDTH - BUTTON_PADDING, 
    BUTTON_PADDING, 
    BUTTON_WIDTH, 
    BUTTON_HEIGHT
)
EXIT_BUTTON_COLOR = (200, 0, 0)
EXIT_BUTTON_BORDER_COLOR = (255, 255, 255)
EXIT_BUTTON_TEXT_COLOR = (255, 255, 255)

# F1 Colors
COLOR_UI_BG = (30, 30, 30)     # Solid dark grey for the UI panel
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

def draw_exit_button(surface):
    pygame.draw.rect(surface, EXIT_BUTTON_COLOR, EXIT_BUTTON_RECT)
    pygame.draw.rect(surface, EXIT_BUTTON_BORDER_COLOR, EXIT_BUTTON_RECT, max(1, int(2 * scale)))
    label = FONT_MAIN.render("Exit", True, EXIT_BUTTON_TEXT_COLOR)
    label_rect = label.get_rect(center=EXIT_BUTTON_RECT.center)
    surface.blit(label, label_rect)

def _monitor_exit_button_thread():
    pressed = False
    while True:
        if quit_flag:
            break
        mouse_pressed = pygame.mouse.get_pressed(num_buttons=3)
        if mouse_pressed[0]:
            if not pressed:
                pressed = True
                mx, my = pygame.mouse.get_pos()
                if EXIT_BUTTON_RECT.collidepoint(mx, my):
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
        else:
            pressed = False
        time.sleep(0.05)

threading.Thread(target=_monitor_exit_button_thread, daemon=True).start()

class Car(pygame.sprite.Sprite):
    def __init__(self, car_id):
        super().__init__()
        self.car_id = car_id
        self.original_image = pygame.image.load(os.path.join("assets", "car.png"))
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

        while length < 200 * self.scale:
            # Important: Limit radar check to TRACK Area (Right Side)
            # x must be greater than TRACK_X_OFFSET and less than SCREEN_WIDTH
            if not (TRACK_X_OFFSET <= x < SCREEN_WIDTH and 0 <= y < SCREEN_HEIGHT):
                break
            
            try:
                if SCREEN.get_at((x, y)) == pygame.Color(2, 105, 31, 255):
                    break
            except IndexError:
                # Safety catch if coordinates are out of bounds
                break

            length += 1
            x = int(self.rect.center[0] + math.cos(math.radians(self.angle + radar_angle)) * length)
            y = int(self.rect.center[1] - math.sin(math.radians(self.angle + radar_angle)) * length)

        # Draw Radar
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
    # Dimensions for the timing tower (fill the UI Width on the LEFT)
    start_x = 0
    start_y = 0
    row_height = 40 * scale
    
    # Header
    header_rect = pygame.Rect(start_x, start_y, UI_WIDTH, row_height)
    pygame.draw.rect(screen, (255, 0, 0), header_rect)
    header_text = FONT_HEADER.render("POS  DRIVER             TIME", True, COLOR_TEXT_WHITE)
    screen.blit(header_text, (start_x + 10, start_y + 10))
    
    # Draw Rows
    for i, car_group in enumerate(cars):
        car = car_group.sprite
        y_pos = start_y + row_height + (i * row_height)
        
        # Color Logic
        text_color = COLOR_TEXT_WHITE
        time_text = ""
        
        if not car.alive:
            text_color = COLOR_TEXT_GREY
            time_text = "DNF"
        else:
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
        
        # Separator Line
        pygame.draw.line(screen, (50, 50, 50), (start_x, y_pos), (UI_WIDTH, y_pos), 1)
        
        # 1. Position
        pos_str = f"{i+1}"
        pos_render = FONT_MAIN.render(pos_str, True, text_color)
        screen.blit(pos_render, (start_x + 10, y_pos + 10))
        
        # 2. Driver Name
        driver_str = f"CAR {car.car_id}"
        driver_render = FONT_MAIN.render(driver_str, True, text_color)
        screen.blit(driver_render, (start_x + 50, y_pos + 10))

        # 3. Time (Adjusted position back to standard layout since bars are gone)
        time_render = FONT_MAIN.render(time_text, True, text_color)
        time_rect = time_render.get_rect(right=UI_WIDTH - 20, top=y_pos + 10)
        screen.blit(time_render, time_rect)

def draw_telemetry_panel(screen, cars):
    # Panel Configuration
    panel_width = 230 * scale
    row_height = 30 * scale
    header_height = 30 * scale
    
    # Calculate Total Height needed (Clamp to screen height if too many cars)
    needed_height = (len(cars) * row_height) + header_height + 10
    total_height = min(needed_height, SCREEN_HEIGHT - 50)
    
    # Bottom Right Position
    start_x = SCREEN_WIDTH - panel_width - 20
    start_y = SCREEN_HEIGHT - total_height - 20
    
    # Draw Background Panel
    s = pygame.Surface((panel_width, total_height))
    s.set_alpha(220)
    s.fill((20, 20, 20))
    screen.blit(s, (start_x, start_y))
    
    # Header
    pygame.draw.rect(screen, (200, 0, 0), (start_x, start_y, panel_width, header_height))
    header_text = FONT_MAIN.render("LIVE TELEMETRY", True, COLOR_TEXT_WHITE)
    screen.blit(header_text, (start_x + 10, start_y + 5))
    
    # Scroll offset if too many cars (simplified: just cut off for now or fit what we can)
    visible_cars = int((total_height - header_height - 10) / row_height)
    
    for i in range(min(len(cars), visible_cars)):
        car_group = cars[i]
        car = car_group.sprite
        y_pos = start_y + header_height + (i * row_height) + 5
        
        # Car ID
        id_text = FONT_MAIN.render(f"{car.car_id}", True, COLOR_TEXT_WHITE if car.alive else COLOR_TEXT_GREY)
        screen.blit(id_text, (start_x + 10, y_pos))
        
        # Telemetry Bars
        telemetry_x = start_x + 50 * scale 
        bar_max_width = 35 * scale
        bar_height = 6 * scale
        
        if car.alive:
            # Accelerator bar (green)
            accel_val = max(0, min(1, car.accelerator))
            accel_width = accel_val * bar_max_width
            pygame.draw.rect(screen, (0, 80, 0), (telemetry_x, y_pos + 8 * scale, bar_max_width, bar_height), 1)
            pygame.draw.rect(screen, COLOR_GREEN, (telemetry_x, y_pos + 8 * scale, accel_width, bar_height))

            # Brake bar (red)
            brake_x = telemetry_x + bar_max_width + 4 * scale
            brake_val = max(0, min(1, car.brake))
            brake_width = brake_val * bar_max_width
            pygame.draw.rect(screen, (80, 0, 0), (brake_x, y_pos + 8 * scale, bar_max_width, bar_height), 1)
            pygame.draw.rect(screen, COLOR_RED, (brake_x, y_pos + 8 * scale, brake_width, bar_height))

            # Steering bar (blue, centered)
            steer_y = y_pos + 18 * scale
            total_steer_width = (bar_max_width * 2) + 4 * scale
            center_x = telemetry_x + (total_steer_width / 2)

            # Neutral reference marks
            pygame.draw.line(screen, (100,100,100), (telemetry_x, steer_y + bar_height/2), (telemetry_x + total_steer_width, steer_y + bar_height/2), 1)
            pygame.draw.line(screen, (200,200,200), (center_x, steer_y), (center_x, steer_y + bar_height), 1)

            # Steering fill based on new unified steering value
            steer = max(-1, min(1, car.steer))
            steer_pixels = steer * (total_steer_width / 2)

            if steer_pixels > 0:    # turning right
                pygame.draw.rect(screen, COLOR_BLUE, (center_x, steer_y, steer_pixels, bar_height))
            else:                   # turning left
                pygame.draw.rect(screen, COLOR_BLUE, (center_x + steer_pixels, steer_y, abs(steer_pixels), bar_height))
        else:
            # Greyed out bars for dead cars
            pygame.draw.rect(screen, COLOR_TEXT_GREY, (telemetry_x, y_pos + 8 * scale, bar_max_width, bar_height), 1)
            pygame.draw.rect(screen, COLOR_TEXT_GREY, (telemetry_x + bar_max_width + 4 * scale, y_pos + 8 * scale, bar_max_width, bar_height), 1)
            pygame.draw.rect(screen, COLOR_TEXT_GREY, (telemetry_x, y_pos + 18 * scale, (bar_max_width * 2) + 4 * scale, bar_height), 1)


def eval_genomes(genomes, config):
    global quit_flag, BEST_OVERALL_LAP, show_telemetry
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
    
    while run and (pygame.time.get_ticks() - start_time) <360000:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_flag = True
                run = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_i:
                    show_telemetry = not show_telemetry

        # 1. Draw Track (Right Side)
        SCREEN.blit(TRACK, (TRACK_X_OFFSET, 0))
        
        # 2. Draw UI Background (Left Side)
        pygame.draw.rect(SCREEN, COLOR_UI_BG, (0, 0, UI_WIDTH, SCREEN_HEIGHT))

        # 3. Update & Draw Cars
        for i, car_group in enumerate(cars):
            car = car_group.sprite
            if not car.alive:
                continue

            raw = nets[i].activate(car.data())
            # Make sure we have 4 outputs
            while len(raw) < 4:
                raw = list(raw) + [0.0]

            # Steering (left/right decision)
            # Steering (left/right decision)
            car.steer_left  = raw[0]
            car.steer_right = raw[1]

            # Combine into a single steering value: right - left
            steer = car.steer_right - car.steer_left

            # Deadzone so tiny jitters don't show as full steering
            if abs(steer) < 0.2:
                steer = 0.0

            # Clamp to [-1, 1] and store
            car.steer = max(-1.0, min(1.0, steer))


            # Pedals: tanh [-1,1] -> [0,1]
            car.brake       = (raw[2] + 1) / 2.0
            car.accelerator = (raw[3] + 1) / 2.0

            # Clamp
            car.brake       = max(0.0, min(1.0, car.brake))
            car.accelerator = max(0.0, min(1.0, car.accelerator))

            # Turn based on strong signal
            if car.steer_left > 0.7:
                car.direction = 1
            elif car.steer_right > 0.7:
                car.direction = -1
            else:
                car.direction = 0

            # Update physics etc.
            car.update()

            # Reward forward movement, not just surviving
            genomes[i][1].fitness += car.speed * 0.01

            car_group.draw(SCREEN)


        # Reward Logic
        for i, car_group in enumerate(cars):
            car = car_group.sprite
            genome = genomes[i][1]

            if car.lap_completed and car.lap_times:
                last_lap = car.lap_times[-1]      # in ms
                lap_seconds = last_lap / 1000.0

                # Fast lap = big reward, slow lap = weak reward
                lap_bonus = 5000.0 / max(lap_seconds, 0.1)

                genome.fitness += lap_bonus

                # Stop the car once it completes the lap (prevents farming)
                car.lap_completed = False
                car.alive = False



        # 4. Draw HUD Overlays
        draw_f1_leaderboard(SCREEN, cars)
        if show_telemetry:
            draw_telemetry_panel(SCREEN, cars)
        draw_exit_button(SCREEN)

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