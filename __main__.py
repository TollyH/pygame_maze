"""
PyGame Maze - Tolly Hill 2022

The main script for the game. Creates and draws to the game window, as well as
receiving and interpreting player input and recording time and movement scores.
"""
import math
import os
import pickle
import sys
from typing import List, Set, Tuple

import pygame

import raycasting
from level import floor_coordinates
from maze_levels import levels

WHITE = (0xFF, 0xFF, 0xFF)
BLACK = (0x00, 0x00, 0x00)
BLUE = (0x00, 0x30, 0xFF)
GOLD = (0xE1, 0xBB, 0x12)
DARK_GOLD = (0x70, 0x5E, 0x09)
GREEN = (0x00, 0xFF, 0x10)
DARK_GREEN = (0x00, 0x80, 0x00)
RED = (0xFF, 0x00, 0x00)
DARK_RED = (0x80, 0x00, 0x00)
PURPLE = (0x87, 0x23, 0xD9)
LILAC = (0xD7, 0xA6, 0xFF)
GREY = (0xAA, 0xAA, 0xAA)
DARK_GREY = (0x20, 0x20, 0x20)

VIEWPORT_WIDTH = 500
VIEWPORT_HEIGHT = 500

DISPLAY_COLUMNS = VIEWPORT_WIDTH
DISPLAY_FOV = 75

DRAW_MAZE_EDGE_AS_WALL = True

TURN_SPEED = 2.5
MOVE_SPEED = 4.0

ALLOW_REALTIME_EDITING = False


def main():
    pygame.init()

    # Minimum window resolution is 500x500
    screen = pygame.display.set_mode(
        (max(VIEWPORT_WIDTH, 500), max(VIEWPORT_HEIGHT + 50, 500))
    )
    pygame.display.set_caption("Maze - Level 1")

    clock = pygame.time.Clock()

    font = pygame.font.SysFont('Tahoma', 24, True)

    facing_directions = [(0.0, 1.0)] * len(levels)
    # Camera planes are always perpendicular to facing directions
    camera_planes = [(-DISPLAY_FOV / 100, 0.0)] * len(levels)
    frame_scores = [0] * len(levels)
    move_scores = [0] * len(levels)
    has_started_level = [False] * len(levels)
    if os.path.isfile("highscores.pickle"):
        with open("highscores.pickle", 'rb') as file:
            highscores: List[Tuple[int, int]] = pickle.load(file)
            if len(highscores) < len(levels):
                highscores += [(0, 0)] * (len(levels) - len(highscores))
    else:
        highscores: List[Tuple[int, int]] = [(0, 0)] * len(levels)

    display_map = False
    display_rays = False
    display_solutions = False

    current_level = 0

    # Game loop
    while True:
        # Limit to 50 FPS
        frame_time = clock.tick(50) / 1000
        display_column_width = VIEWPORT_WIDTH // DISPLAY_COLUMNS
        tile_width = VIEWPORT_WIDTH // levels[current_level].dimensions[0]
        tile_height = VIEWPORT_HEIGHT // levels[current_level].dimensions[1]
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            # Standard "press-once" keys
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFTBRACKET,
                                 pygame.K_RIGHTBRACKET):
                    if event.key == pygame.K_LEFTBRACKET and current_level > 0:
                        current_level -= 1
                    elif (event.key == pygame.K_RIGHTBRACKET
                            and current_level < len(levels) - 1):
                        current_level += 1
                    else:
                        continue
                    # Adjust tile width and height for new level
                    tile_width = (
                        VIEWPORT_WIDTH // levels[current_level].dimensions[0]
                    )
                    tile_height = (
                        VIEWPORT_HEIGHT // levels[current_level].dimensions[1]
                    )
                    pygame.display.set_caption(
                        f"Maze - Level {current_level + 1}"
                    )
                elif event.key == pygame.K_r:
                    levels[current_level].reset()
                    facing_directions[current_level] = (0.0, 1.0)
                    camera_planes[current_level] = (-DISPLAY_FOV / 100, 0.0)
                    frame_scores[current_level] = 0
                    move_scores[current_level] = 0
                    has_started_level[current_level] = False
                elif event.key == pygame.K_SPACE:
                    pressed = pygame.key.get_pressed()
                    if pressed[pygame.K_RCTRL] or pressed[pygame.K_LCTRL]:
                        display_rays = not display_rays
                    elif pressed[pygame.K_RALT] or pressed[pygame.K_LALT]:
                        display_solutions = not display_solutions
                    else:
                        display_map = not display_map
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mouse_coords = pygame.mouse.get_pos()
                if (ALLOW_REALTIME_EDITING
                        and event.button == pygame.BUTTON_LEFT
                        and mouse_coords[0] > VIEWPORT_WIDTH):
                    clicked_tile = (
                        (mouse_coords[0] - VIEWPORT_WIDTH) // tile_width,
                        (mouse_coords[1] - 50) // tile_height
                    )
                    levels[current_level][clicked_tile] = (
                        not levels[current_level][clicked_tile]
                    )

        if (display_map
                and screen.get_size()[0] < VIEWPORT_WIDTH * 2):
            screen = pygame.display.set_mode(
                (
                    max(VIEWPORT_WIDTH * 2, 500),
                    max(VIEWPORT_HEIGHT + 50, 500)
                )
            )
        elif (not display_map
                and screen.get_size()[0] > VIEWPORT_WIDTH):
            screen = pygame.display.set_mode(
                (
                    max(VIEWPORT_WIDTH, 500),
                    max(VIEWPORT_HEIGHT + 50, 500)
                )
            )

        old_grid_position = floor_coordinates(
            levels[current_level].player_coords
        )
        # Ensure framerate does not affect speed values
        turn_speed_mod = frame_time * TURN_SPEED
        move_speed_mod = frame_time * MOVE_SPEED
        # Held down keys
        pressed_keys = pygame.key.get_pressed()
        if pressed_keys[pygame.K_w] or pressed_keys[pygame.K_UP]:
            if not levels[current_level].won:
                levels[current_level].move_player((
                    facing_directions[current_level][0] * move_speed_mod,
                    facing_directions[current_level][1] * move_speed_mod
                ))
                has_started_level[current_level] = True
        if pressed_keys[pygame.K_s] or pressed_keys[pygame.K_DOWN]:
            if not levels[current_level].won:
                levels[current_level].move_player((
                    -facing_directions[current_level][0] * move_speed_mod,
                    -facing_directions[current_level][1] * move_speed_mod
                ))
                has_started_level[current_level] = True
        if pressed_keys[pygame.K_a]:
            if not levels[current_level].won:
                levels[current_level].move_player((
                    facing_directions[current_level][1] * move_speed_mod,
                    -facing_directions[current_level][0] * move_speed_mod
                ))
                has_started_level[current_level] = True
        if pressed_keys[pygame.K_d]:
            if not levels[current_level].won:
                levels[current_level].move_player((
                    -facing_directions[current_level][1] * move_speed_mod,
                    facing_directions[current_level][0] * move_speed_mod
                ))
                has_started_level[current_level] = True
        if pressed_keys[pygame.K_RIGHT]:
            old_direction = facing_directions[current_level]
            facing_directions[current_level] = (
                old_direction[0] * math.cos(turn_speed_mod)
                - old_direction[1] * math.sin(turn_speed_mod),
                old_direction[0] * math.sin(turn_speed_mod)
                + old_direction[1] * math.cos(turn_speed_mod)
            )
            old_camera_plane = camera_planes[current_level]
            camera_planes[current_level] = (
                old_camera_plane[0] * math.cos(turn_speed_mod)
                - old_camera_plane[1] * math.sin(turn_speed_mod),
                old_camera_plane[0] * math.sin(turn_speed_mod)
                + old_camera_plane[1] * math.cos(turn_speed_mod)
            )
        if pressed_keys[pygame.K_LEFT]:
            old_direction = facing_directions[current_level]
            facing_directions[current_level] = (
                old_direction[0] * math.cos(-turn_speed_mod)
                - old_direction[1] * math.sin(-turn_speed_mod),
                old_direction[0] * math.sin(-turn_speed_mod)
                + old_direction[1] * math.cos(-turn_speed_mod)
            )
            old_camera_plane = camera_planes[current_level]
            camera_planes[current_level] = (
                old_camera_plane[0] * math.cos(-turn_speed_mod)
                - old_camera_plane[1] * math.sin(-turn_speed_mod),
                old_camera_plane[0] * math.sin(-turn_speed_mod)
                + old_camera_plane[1] * math.cos(-turn_speed_mod)
            )
        # Only count up one move score if player crossed a gridline
        if floor_coordinates(
                levels[current_level].player_coords) != old_grid_position:
            move_scores[current_level] += 1

        if levels[current_level].won:
            highscores_updated = False
            if (frame_scores[current_level] < highscores[current_level][0]
                    or highscores[current_level][0] == 0):
                highscores[current_level] = (
                    frame_scores[current_level], highscores[current_level][1]
                )
                highscores_updated = True
            if (move_scores[current_level] < highscores[current_level][1]
                    or highscores[current_level][1] == 0):
                highscores[current_level] = (
                    highscores[current_level][0], move_scores[current_level]
                )
                highscores_updated = True
            if highscores_updated and not os.path.isdir("highscores.pickle"):
                with open("highscores.pickle", 'wb') as file:
                    pickle.dump(highscores, file)
            screen.fill(GREEN)
            time_score_text = font.render(
                f"Time Score: {frame_scores[current_level]}",
                True, BLUE
            )
            move_score_text = font.render(
                f"Move Score: {move_scores[current_level]}",
                True, BLUE
            )
            best_time_score_text = font.render(
                f"Best Time Score: {highscores[current_level][0]}",
                True, BLUE
            )
            best_move_score_text = font.render(
                f"Best Move Score: {highscores[current_level][1]}",
                True, BLUE
            )
            best_total_time_score_text = font.render(
                f"Best Game Time Score: {sum(x[0] for x in highscores)}",
                True, BLUE
            )
            best_total_move_score_text = font.render(
                f"Best Game Move Score: {sum(x[1] for x in highscores)}",
                True, BLUE
            )
            lower_hint_text = font.render(
                "(Lower scores are better)", True, BLUE
            )
            screen.blit(time_score_text, (10, 10))
            screen.blit(move_score_text, (10, 40))
            screen.blit(best_time_score_text, (10, 90))
            screen.blit(best_move_score_text, (10, 120))
            screen.blit(best_total_time_score_text, (10, 200))
            screen.blit(best_total_move_score_text, (10, 230))
            screen.blit(lower_hint_text, (10, 280))
        else:
            if has_started_level[current_level]:
                frame_scores[current_level] += 1
            screen.fill(GREY)
            time_score_text = font.render(
                f"Time: {frame_scores[current_level]}"
                if has_started_level[current_level] else
                f"Time: {highscores[current_level][0]}",
                True, WHITE
            )
            move_score_text = font.render(
                f"Moves: {move_scores[current_level]}"
                if has_started_level[current_level] else
                f"Moves: {highscores[current_level][1]}",
                True, WHITE
            )
            starting_keys = len(levels[current_level].original_exit_keys)
            remaining_keys = (
                starting_keys - len(levels[current_level].exit_keys)
            )
            keys_text = font.render(
                f"Keys: {remaining_keys}/{starting_keys}", True, WHITE
            )
            screen.blit(time_score_text, (10, 10))
            screen.blit(move_score_text, (180, 10))
            screen.blit(keys_text, (340, 10))
            # Ceiling
            pygame.draw.rect(
                screen, BLUE,
                (0, 50, VIEWPORT_WIDTH, VIEWPORT_HEIGHT // 2)
            )
            # Floor
            pygame.draw.rect(
                screen, WHITE,
                (
                    0, VIEWPORT_HEIGHT // 2 + 50,
                    VIEWPORT_WIDTH, VIEWPORT_HEIGHT // 2
                )
            )

            ray_end_coords: List[Tuple[float, float]] = []
            for index, (coord, distance, side_was_ns, hit_type) in enumerate(
                    raycasting.get_columns(
                        DISPLAY_COLUMNS, levels[current_level],
                        DRAW_MAZE_EDGE_AS_WALL,
                        facing_directions[current_level],
                        camera_planes[current_level])):
                # Edge of maze when drawing maze edges as walls is disabled
                if distance == float('inf'):
                    continue
                ray_end_coords.append(coord)
                # Prevent division by 0
                distance = max(1e-30, distance)
                column_height = round(VIEWPORT_HEIGHT / distance)
                column_height = min(column_height, VIEWPORT_HEIGHT)
                if hit_type == raycasting.WALL:
                    colour = DARK_GREY if side_was_ns else BLACK
                elif hit_type == raycasting.END_POINT:
                    colour = GREEN if side_was_ns else DARK_GREEN
                elif hit_type == raycasting.KEY:
                    colour = GOLD if side_was_ns else DARK_GOLD
                else:
                    continue
                pygame.draw.rect(
                    screen, colour, (
                        display_column_width * index,
                        max(
                            0, -column_height // 2 + VIEWPORT_HEIGHT // 2
                        ) + 50,
                        display_column_width, column_height
                    )
                )
            if display_map:
                solutions: List[List[Tuple[int, int]]] = []
                # A set of all coordinates appearing in any solution
                solution_coords: Set[Tuple[int, int]] = set()
                if display_solutions and not ALLOW_REALTIME_EDITING:
                    solutions = levels[current_level].find_possible_paths()
                    solution_coords = {x for y in solutions[1:] for x in y}
                for y, row in enumerate(levels[current_level].wall_map):
                    for x, point in enumerate(row):
                        if floor_coordinates(
                                levels[current_level].player_coords) == (x, y):
                            color = BLUE
                        elif (x, y) in levels[current_level].exit_keys:
                            color = GOLD
                        elif levels[current_level].start_point == (x, y):
                            color = RED
                        elif levels[current_level].end_point == (x, y):
                            color = GREEN
                        elif len(solutions) >= 1 and (x, y) in solutions[0]:
                            color = PURPLE
                        elif len(solutions) >= 1 and (x, y) in solution_coords:
                            color = LILAC
                        else:
                            color = BLACK if point else WHITE
                        pygame.draw.rect(
                            screen, color, (
                                tile_width * x + VIEWPORT_WIDTH,
                                tile_height * y + 50, tile_width, tile_height
                            )
                        )
                # Raycast rays
                if display_rays:
                    for point in ray_end_coords:
                        pygame.draw.line(
                            screen, DARK_GOLD, (
                                levels[current_level].player_coords[0]
                                * tile_width + VIEWPORT_WIDTH,
                                levels[current_level].player_coords[1]
                                * tile_height + 50
                            ),
                            (
                                point[0] * tile_width + VIEWPORT_WIDTH,
                                point[1] * tile_height + 50
                            ), 1
                        )
                # Player direction
                pygame.draw.line(
                    screen, DARK_RED, (
                        levels[current_level].player_coords[0] * tile_width
                        + VIEWPORT_WIDTH,
                        levels[current_level].player_coords[1] * tile_height
                        + 50
                    ),
                    (
                        levels[current_level].player_coords[0] * tile_width
                        + VIEWPORT_WIDTH
                        + facing_directions[current_level][0] * tile_width
                        // 2,
                        levels[current_level].player_coords[1] * tile_height
                        + 50 + facing_directions[current_level][1] * tile_width
                        // 2
                    ), 3
                )
                # Exact player position
                pygame.draw.circle(
                    screen, DARK_GREEN, (
                        levels[current_level].player_coords[0] * tile_width
                        + VIEWPORT_WIDTH,
                        levels[current_level].player_coords[1] * tile_height
                        + 50
                    ), tile_width // 8
                )
        print(
            f"\r{clock.get_fps():5.2f} FPS - "
            + f"Position ({levels[current_level].player_coords[0]:5.2f},"
            + f"{levels[current_level].player_coords[1]:5.2f}) - "
            + f"Direction ({facing_directions[current_level][0]:5.2f},"
            + f"{facing_directions[current_level][1]:5.2f}) - "
            + f"Camera ({camera_planes[current_level][0]:5.2f},"
            + f"{camera_planes[current_level][1]:5.2f})",
            end="", flush=True
        )
        pygame.display.flip()


if __name__ == "__main__":
    main()
