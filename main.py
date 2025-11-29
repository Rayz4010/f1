import pygame
import neat
import os
import sys
import math


screen_width=800
screen_height=600


Screen = pygame.display.set_mode((screen_width, screen_height))
Track = pygame.image.load(os.path.join("assets","track.png"))
pygame.init()

clock = pygame.time.Clock() 
running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    Screen.fill(Track)  # Draw the track image
    pygame.display.flip()   # Update the full display surface to the screen
    clock.tick(60)         # Limit to 60 frames per second
    
pygame.quit()