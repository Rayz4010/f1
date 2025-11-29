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

TRACK = pygame.image.load(os.path.join("assets", "track.png"))
original_width, original_height = TRACK.get_width(), TRACK.get_height()
TRACK = pygame.transform.scale(TRACK, (SCREEN_WIDTH, SCREEN_HEIGHT))
scale_x = SCREEN_WIDTH / original_width
scale_y = SCREEN_HEIGHT / original_height
scale = min(scale_x, scale_y)  # Use minimum scale to avoid distortion in distances

# Add font for timer display (scale font size to screen)
FONT = pygame.font.SysFont(None, int(24 * scale))

quit_flag = False

# Exit button setup (drawn on TRACK so it appears every frame)
BUTTON_PADDING = int(20 * scale)
BUTTON_WIDTH = int(140 * scale)
BUTTON_HEIGHT = int(48 * scale)
EXIT_BUTTON_RECT = pygame.Rect(SCREEN_WIDTH - BUTTON_PADDING - BUTTON_WIDTH, BUTTON_PADDING, BUTTON_WIDTH, BUTTON_HEIGHT)
EXIT_BUTTON_COLOR = (200, 0, 0)
EXIT_BUTTON_BORDER_COLOR = (255, 255, 255)
EXIT_BUTTON_TEXT_COLOR = (255, 255, 255)

def draw_exit_button(surface):
    # Draw background rect and border onto provided surface (TRACK)
    pygame.draw.rect(surface, EXIT_BUTTON_COLOR, EXIT_BUTTON_RECT)
    pygame.draw.rect(surface, EXIT_BUTTON_BORDER_COLOR, EXIT_BUTTON_RECT, max(1, int(2 * scale)))
    label = FONT.render("Exit", True, EXIT_BUTTON_TEXT_COLOR)
    label_rect = label.get_rect(center=EXIT_BUTTON_RECT.center)
    surface.blit(label, label_rect)

# Draw button once on TRACK (it will be part of the background each frame)
draw_exit_button(TRACK)


def _monitor_exit_button_thread():
    """Background thread: watches for left mouse clicks inside the exit button rect and posts a QUIT event."""
    pressed = False
    while True:
        # If main loop requested stop, exit thread
        if quit_flag:
            break

        mouse_pressed = pygame.mouse.get_pressed(num_buttons=3)
        if mouse_pressed[0]:
            if not pressed:
                pressed = True
                mx, my = pygame.mouse.get_pos()
                if EXIT_BUTTON_RECT.collidepoint(mx, my):
                    # Post a QUIT event - main loop will pick this up and set quit_flag
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
        else:
            pressed = False

        time.sleep(0.05)

# Start the thread to monitor clicks on the exit button
threading.Thread(target=_monitor_exit_button_thread, daemon=True).start()

class Car(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.original_image = pygame.image.load(os.path.join("assets", "car.png"))
        car_scale = scale * 0.2  # Reduce car size further (changed from 0.5 to 0.25)
        self.original_image = pygame.transform.scale(self.original_image, (int(self.original_image.get_width() * car_scale), int(self.original_image.get_height() * car_scale)))
        self.image = self.original_image
        self.start_pos = (490 * scale_x, 820 * scale_y)
        self.rect = self.image.get_rect(center=self.start_pos)
        self.vel_vector = pygame.math.Vector2(0.8, 0)
        self.angle = 0
        self.rotation_vel = 5
        self.direction = 0
        self.alive = True
        self.radars = []
        self.lap_started = False
        self.lap_completed = False
        self.lap_time = 0
        self.lap_start_time = 0
        self.lap_times = []
        self.speed = 6  # Initial speed multiplier
        self.steer_left = 0
        self.steer_right = 0
        self.brake = 0
        self.accelerator = 0
        self.scale = scale

    def update(self):
        self.radars.clear()
        self.drive()
        self.check_lap()
        self.rotate()
        for radar_angle in (-60, -30, 0, 30, 60):
            self.radar(radar_angle)
        self.collision()
        self.data()

    def drive(self):
        # Adjust speed based on accelerator and brake
        self.speed += (self.accelerator - self.brake) * 0.1
        self.speed = max(0, min(20, self.speed))  # Clamp speed
        self.rect.center += self.vel_vector * self.speed

    def check_lap(self):
        if not self.lap_started:
            if math.sqrt((self.rect.center[0] - self.start_pos[0])**2 + (self.rect.center[1] - self.start_pos[1])**2) > 50 * self.scale:
                self.lap_started = True
                self.lap_start_time = pygame.time.get_ticks()
        if self.lap_started and not self.lap_completed:
            if math.sqrt((self.rect.center[0] - self.start_pos[0])**2 + (self.rect.center[1] - self.start_pos[1])**2) < 50 * self.scale:
                self.lap_completed = True
                self.lap_time = pygame.time.get_ticks() - self.lap_start_time
                self.lap_times.append(self.lap_time)
                self.speed += 1  # Increase speed after each lap
                self.lap_started = False
                self.lap_completed = False
                self.lap_start_time = 0

    def collision(self):
        length = 40 * self.scale
        collision_point_right = [int(self.rect.center[0] + math.cos(math.radians(self.angle + 18)) * length),
                                 int(self.rect.center[1] - math.sin(math.radians(self.angle + 18)) * length)]
        collision_point_left = [int(self.rect.center[0] + math.cos(math.radians(self.angle - 18)) * length),
                                int(self.rect.center[1] - math.sin(math.radians(self.angle - 18)) * length)]

        # Die on Collision
        if SCREEN.get_at(collision_point_right) == pygame.Color(2, 105, 31, 255) \
                or SCREEN.get_at(collision_point_left) == pygame.Color(2, 105, 31, 255):
            self.alive = False

        # Draw Collision Points
        pygame.draw.circle(SCREEN, (0, 255, 255, 0), collision_point_right, 4)
        pygame.draw.circle(SCREEN, (0, 255, 255, 0), collision_point_left, 4)

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
            if not (0 <= x < SCREEN_WIDTH and 0 <= y < SCREEN_HEIGHT):
                break
            if SCREEN.get_at((x, y)) == pygame.Color(2, 105, 31, 255):
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


def draw_bar(screen, x, y, width, height, value, label):
    value = max(0, min(1, value))
    pygame.draw.rect(screen, (255, 0, 0), (x, y, width, height), 2)
    fill_width = int(width * value)
    pygame.draw.rect(screen, (0, 255, 0), (x, y, fill_width, height))
    text = FONT.render(label, True, (255, 255, 255))
    screen.blit(text, (x, y + height + 5))


def eval_genomes(genomes, config):
    global quit_flag
    cars = []
    nets = []
    for _, genome in genomes:
        car_group = pygame.sprite.GroupSingle(Car())
        cars.append(car_group)
        net = neat.nn.FeedForwardNetwork.create(genome, config)
        nets.append(net)
        genome.fitness = 0
    clock = pygame.time.Clock()
    start_time = pygame.time.get_ticks()
    run = True
    while run and not any(car_group.sprite.lap_completed for car_group in cars) and (pygame.time.get_ticks() - start_time) < 360000:  # Stop when any car completes a lap or 30 seconds
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_flag = True
                run = False

        SCREEN.blit(TRACK, (0, 0))

        for i, car_group in enumerate(cars):
            car = car_group.sprite
            if car.alive:
                output = nets[i].activate(car.data())
                car.steer_left = output[0] if len(output) > 0 else 0
                car.steer_right = output[1] if len(output) > 1 else 0
                car.brake = output[2] if len(output) > 2 else 0
                car.accelerator = output[3] if len(output) > 3 else 0
                if car.steer_left > 0.7:
                    car.direction = 1
                if car.steer_right > 0.7:
                    car.direction = -1
                if car.steer_left <= 0.7 and car.steer_right <= 0.7:
                    car.direction = 0
                car.update()
                genomes[i][1].fitness += 1
                car_group.draw(SCREEN)

        # Reward for completing laps
        for i, car_group in enumerate(cars):
            car = car_group.sprite
            if car.lap_completed:
                genomes[i][1].fitness += 10000 - car.lap_time
                car.lap_completed = False

        # Display timers
        for i, car_group in enumerate(cars):
            car = car_group.sprite
            if car.alive:
                if car.lap_started:
                    current_time = (pygame.time.get_ticks() - car.lap_start_time) / 1000
                    timer_text = FONT.render(f"Car {i+1} Lap {len(car.lap_times)+1} Time: {current_time:.2f}s", True, (255, 255, 255))
                    SCREEN.blit(timer_text, (10, 10 + i * 30))
                elif len(car.lap_times) > 0:
                    last_time = car.lap_times[-1] / 1000
                    timer_text = FONT.render(f"Car {i+1} Last Lap: {last_time:.2f}s", True, (255, 255, 255))
                    SCREEN.blit(timer_text, (10, 10 + i * 30))

        pygame.display.update()
        clock.tick(60)

        if all(not car_group.sprite.alive for car_group in cars):
            run = False

    if quit_flag:
        raise KeyboardInterrupt


# Setup NEAT Neural Network
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
