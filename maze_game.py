"""
The main script for the game. Creates the game window, receives and interprets
player input, and records time and movement scores. Also handles time-based
events such as monster movement and spawning.
"""
import math
import os
import pickle
import random
import sys
import threading
from glob import glob
from typing import Dict, List, Optional, Set, Tuple, Union

import pygame

import config_editor
import config_loader
import level
import maze_levels
import raycasting
import screen_drawing


def maze_game(*, level_json_path: str = "maze_levels.json",
              config_ini_path: str = "config.ini",
              process_command_args: bool = False) -> None:
    """
    Main function for the maze game. Manages all input, output, and timing.
    """
    # Change working directory to the directory where the script is located.
    # This prevents issues with required files not being found.
    os.chdir(os.path.dirname(__file__))
    pygame.init()

    if process_command_args:
        for arg in sys.argv[1:]:
            arg_pair = arg.split("=")
            if len(arg_pair) == 2:
                lower_key = arg_pair[0].lower()
                if lower_key in ("--level-json-path", "-p"):
                    level_json_path = arg_pair[1]
                    continue
                if lower_key in ("--config-ini-path", "-c"):
                    config_ini_path = arg_pair[1]
                    continue
            print(f"Unknown argument or missing value: '{arg}'")
            sys.exit(1)

    last_config_edit = os.path.getmtime('config.ini')
    cfg = config_loader.Config(config_ini_path)

    levels = maze_levels.load_level_json(level_json_path)

    # Minimum window resolution is 500×500
    screen = pygame.display.set_mode((
        max(cfg.viewport_width, 500), max(cfg.viewport_height, 500)
    ))
    pygame.display.set_caption("PyMaze - Level 1")
    pygame.display.set_icon(
        pygame.image.load(os.path.join("window_icons", "main.png")).convert()
    )

    clock = pygame.time.Clock()

    try:
        placeholder_texture = pygame.image.load(
            os.path.join("textures", "placeholder.png")
        ).convert_alpha()
    except FileNotFoundError:
        placeholder_texture = pygame.Surface(
            (cfg.texture_width, cfg.texture_height)
        )

    # X+Y facing directions, times, moves, etc. are specific to each level,
    # so are each stored in a list.
    facing_directions = [(0.0, 1.0)] * len(levels)
    # Camera planes are always perpendicular to facing directions
    camera_planes = [(-cfg.display_fov / 100, 0.0)] * len(levels)
    time_scores = [0.0] * len(levels)
    move_scores = [0.0] * len(levels)
    has_started_level = [False] * len(levels)
    if os.path.isfile("highscores.pickle"):
        with open("highscores.pickle", 'rb') as file:
            highscores: List[Tuple[float, float]] = pickle.load(file)
            if len(highscores) < len(levels):
                highscores += [(0.0, 0.0)] * (len(levels) - len(highscores))
    else:
        highscores = [(0.0, 0.0)] * len(levels)

    # Used to create the darker versions of each texture
    darkener = pygame.Surface((cfg.texture_width, cfg.texture_height))
    darkener.fill(screen_drawing.BLACK)
    darkener.set_alpha(127)
    # {texture_name: (light_texture, dark_texture)}
    wall_textures: Dict[str, Tuple[pygame.Surface, pygame.Surface]] = {
        os.path.split(x)[-1].split(".")[0]:
            (pygame.image.load(x).convert(), pygame.image.load(x).convert())
        for x in glob(os.path.join("textures", "wall", "*.png"))
    }
    wall_textures["placeholder"] = (
        placeholder_texture, placeholder_texture.copy()
    )
    for _, (_, surface_to_dark) in wall_textures.items():
        surface_to_dark.blit(darkener, (0, 0))

    # {texture_name: texture}
    decoration_textures: Dict[str, pygame.Surface] = {
        os.path.split(x)[-1].split(".")[0]:
            pygame.image.load(x).convert_alpha()
        for x in glob(
            os.path.join("textures", "sprite", "decoration", "*.png"))
    }
    decoration_textures["placeholder"] = placeholder_texture

    # {degradation_stage: (light_texture, dark_texture)}
    player_wall_textures: Dict[int, Tuple[pygame.Surface, pygame.Surface]] = {
        # Parse player wall texture surfaces to integer
        int(os.path.split(x)[-1].split(".")[0]):
            (pygame.image.load(x).convert(), pygame.image.load(x).convert())
        for x in glob(os.path.join("textures", "player_wall", "*.png"))
    }
    if len(player_wall_textures) == 0:
        player_wall_textures[0] = (
            placeholder_texture, placeholder_texture.copy()
        )
    for _, (_, surface_to_dark) in player_wall_textures.items():
        surface_to_dark.blit(darkener, (0, 0))

    try:
        sky_texture = pygame.image.load(
            os.path.join("textures", "sky.png")
        ).convert_alpha()
    except FileNotFoundError:
        sky_texture = placeholder_texture

    # {raycasting.CONSTANT_VALUE: sprite_texture}
    sprite_textures = {
        getattr(raycasting, os.path.split(x)[-1].split(".")[0].upper()):
            pygame.image.load(x).convert_alpha()
        for x in glob(os.path.join("textures", "sprite", "*.png"))
    }

    blank_icon = pygame.Surface((32, 32))
    # {screen_drawing.CONSTANT_VALUE: icon_texture}
    hud_icons = {
        getattr(screen_drawing, os.path.split(x)[-1].split(".")[0].upper()):
            pygame.transform.scale(
                pygame.image.load(x).convert_alpha(), (32, 32)
            )
        for x in glob(os.path.join('textures', 'hud_icons', '*.png'))
    }

    try:
        first_person_gun = pygame.transform.scale(
            pygame.image.load(
                os.path.join('textures', 'gun_fp.png')
            ).convert_alpha(),
            (cfg.viewport_width, cfg.viewport_height)
        )
    except FileNotFoundError:
        first_person_gun = pygame.Surface(
            (cfg.viewport_width, cfg.viewport_height)
        )

    try:
        jumpscare_monster_texture = pygame.transform.scale(
            pygame.image.load(
                os.path.join("textures", "death_monster.png")
            ).convert_alpha(),
            (cfg.viewport_width, cfg.viewport_height)
        )
    except FileNotFoundError:
        jumpscare_monster_texture = pygame.transform.scale(
            placeholder_texture,
            (cfg.viewport_width, cfg.viewport_height)
        )

    audio_error_occurred = False
    try:
        monster_jumpscare_sound: Union[
            pygame.mixer.Sound, EmptySound
        ] = pygame.mixer.Sound(
            os.path.join("sounds", "monster_jumpscare.wav")
        )
        monster_spotted_sound: Union[
            pygame.mixer.Sound, EmptySound
        ] = pygame.mixer.Sound(
            os.path.join("sounds", "monster_spotted.wav")
        )
        # {min_distance_to_play: Sound}
        # Must be in ascending numerical order.
        breathing_sounds: Dict[int, Union[
            pygame.mixer.Sound, EmptySound
        ]] = {
            0: pygame.mixer.Sound(
                os.path.join("sounds", "player_breathe", "heavy.wav")
            ),
            5: pygame.mixer.Sound(
                os.path.join("sounds", "player_breathe", "medium.wav")
            ),
            10: pygame.mixer.Sound(
                os.path.join("sounds", "player_breathe", "light.wav")
            )
        }
        if len(breathing_sounds) == 0:
            raise FileNotFoundError("No breathing sounds found")
        footstep_sounds: List[Union[
            pygame.mixer.Sound, EmptySound
        ]] = [
            pygame.mixer.Sound(x)
            for x in glob(os.path.join("sounds", "footsteps", "*.wav"))
        ]
        if len(footstep_sounds) == 0:
            raise FileNotFoundError("No footstep sounds found")
        monster_roam_sounds: List[Union[
            pygame.mixer.Sound, EmptySound
        ]] = [
            pygame.mixer.Sound(x)
            for x in glob(os.path.join("sounds", "monster_roam", "*.wav"))
        ]
        if len(monster_roam_sounds) == 0:
            raise FileNotFoundError("No monster roam sounds found")
        key_pickup_sounds: List[Union[
            pygame.mixer.Sound, EmptySound
        ]] = [
            pygame.mixer.Sound(x)
            for x in glob(os.path.join("sounds", "key_pickup", "*.wav"))
        ]
        key_sensor_pickup_sound: Union[
            pygame.mixer.Sound, EmptySound
        ] = pygame.mixer.Sound(os.path.join("sounds", "sensor_pickup.wav"))
        gun_pickup_sound: Union[
            pygame.mixer.Sound, EmptySound
        ] = pygame.mixer.Sound(os.path.join("sounds", "gun_pickup.wav"))
        if len(key_pickup_sounds) == 0:
            raise FileNotFoundError("No key pickup sounds found")
        flag_place_sounds: List[Union[
            pygame.mixer.Sound, EmptySound
        ]] = [
            pygame.mixer.Sound(x)
            for x in glob(os.path.join("sounds", "flag_place", "*.wav"))
        ]
        if len(flag_place_sounds) == 0:
            raise FileNotFoundError("No flag place sounds found")
        wall_place_sounds: List[Union[
            pygame.mixer.Sound, EmptySound
        ]] = [
            pygame.mixer.Sound(x)
            for x in glob(os.path.join("sounds", "wall_place", "*.wav"))
        ]
        if len(wall_place_sounds) == 0:
            raise FileNotFoundError("No wall place sounds found")
        compass_open_sound: Union[
            pygame.mixer.Sound, EmptySound
        ] = pygame.mixer.Sound(os.path.join("sounds", "compass_open.wav"))
        compass_close_sound: Union[
            pygame.mixer.Sound, EmptySound
        ] = pygame.mixer.Sound(os.path.join("sounds", "compass_close.wav"))
        map_open_sound: Union[
            pygame.mixer.Sound, EmptySound
        ] = pygame.mixer.Sound(os.path.join("sounds", "map_open.wav"))
        map_close_sound: Union[
            pygame.mixer.Sound, EmptySound
        ] = pygame.mixer.Sound(os.path.join("sounds", "map_close.wav"))
        gunshot_sound: Union[
            pygame.mixer.Sound, EmptySound
        ] = pygame.mixer.Sound(os.path.join("sounds", "gunshot.wav"))
        # Constant ambient sound — loops infinitely
        pygame.mixer.music.load(os.path.join("sounds", "ambience.wav"))
        light_flicker_sound: Union[
            pygame.mixer.Sound, EmptySound
        ] = pygame.mixer.Sound(
            os.path.join("sounds", "light_flicker.wav")
        )
    except (FileNotFoundError, pygame.error):
        audio_error_occurred = True
        empty_sound = EmptySound()
        monster_jumpscare_sound = empty_sound
        monster_spotted_sound = empty_sound
        breathing_sounds = {0: empty_sound}
        footstep_sounds = [empty_sound]
        monster_roam_sounds = [empty_sound]
        key_pickup_sounds = [empty_sound]
        key_sensor_pickup_sound = empty_sound
        gun_pickup_sound = empty_sound
        flag_place_sounds = [empty_sound]
        wall_place_sounds = [empty_sound]
        compass_open_sound = empty_sound
        compass_close_sound = empty_sound
        map_open_sound = empty_sound
        map_close_sound = empty_sound
        gunshot_sound = empty_sound
        light_flicker_sound = empty_sound
    time_to_breathing_finish = 0.0
    time_to_next_roam_sound = 0.0

    enable_mouse_control = False
    # Used to calculate how far mouse has travelled for mouse control.
    old_mouse_pos = (cfg.viewport_width // 2, cfg.viewport_height // 2)

    display_map = False
    display_compass = False
    display_stats = True
    display_rays = False

    is_reset_prompt_shown = False

    current_level = 0
    monster_timeouts = [0.0] * len(levels)
    # How long since the monster was last spotted. Used to prevent the
    # "spotted" jumpscare sound playing repeatedly.
    monster_spotted = [cfg.monster_spot_timeout] * len(levels)
    monster_escape_time = [cfg.monster_time_to_escape] * len(levels)
    # -1 means that the monster has not currently caught the player.
    monster_escape_clicks = [-1] * len(levels)
    compass_times = [cfg.compass_time] * len(levels)
    compass_burned_out = [False] * len(levels)
    compass_charge_delays = [cfg.compass_charge_delay] * len(levels)
    key_sensor_times = [0.0] * len(levels)
    has_gun = [False] * len(levels)
    wall_place_cooldown = [0.0] * len(levels)
    flicker_time_remaining = [0.0] * len(levels)
    pickup_flash_time_remaining = 0.0

    # [None | (grid_x, grid_y, time_of_placement)]
    player_walls: List[Optional[Tuple[int, int, float]]] = [None] * len(levels)

    # Used to draw level behind victory/reset screens without having to raycast
    # during every new frame.
    last_level_frame = [
        pygame.Surface((cfg.viewport_width, cfg.viewport_height))
        for _ in range(len(levels))
    ]

    # Game loop
    while True:
        screen.fill(screen_drawing.BLACK)
        if os.path.getmtime('config.ini') > last_config_edit:
            # Config has been edited so it should be reloaded.
            last_config_edit = os.path.getmtime('config.ini')
            cfg = config_loader.Config(config_ini_path)
        # Limit FPS and record time last frame took to render
        frame_time = clock.tick(cfg.frame_rate_limit) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if __name__ == "__main__":
                    pygame.quit()
                    sys.exit()
                pygame.mixer.music.unload()
                pygame.display.set_caption("PyMaze")
                # Return the mouse to normal if it is currently captured
                if enable_mouse_control:
                    pygame.mouse.set_visible(True)
                    pygame.event.set_grab(False)
                return
            # Standard "press-once" keys
            elif event.type == pygame.KEYDOWN:
                # Never stop the user regaining control of their mouse with
                # escape.
                if event.key == pygame.K_ESCAPE and enable_mouse_control:
                    enable_mouse_control = False
                    # Return the mouse to normal
                    pygame.mouse.set_visible(True)
                    pygame.event.set_grab(False)
                elif not is_reset_prompt_shown:
                    if monster_escape_clicks[current_level] >= 0:
                        if event.key == pygame.K_w:
                            monster_escape_clicks[current_level] += 1
                            if (monster_escape_clicks[current_level]
                                    >= cfg.monster_presses_to_escape):
                                monster_escape_clicks[current_level] = -1
                                levels[current_level].monster_coords = None
                    if event.key == pygame.K_f:
                        if (not levels[current_level].won
                                or levels[current_level].killed):
                            grid_coords = level.floor_coordinates(
                                levels[current_level].player_coords
                            )
                            if (grid_coords in
                                    levels[current_level].player_flags):
                                levels[current_level].player_flags.remove(
                                    grid_coords
                                )
                            else:
                                levels[current_level].player_flags.add(
                                    grid_coords
                                )
                                random.choice(flag_place_sounds).play()
                    elif event.key == pygame.K_c:
                        # Compass and map cannot be displayed together
                        if (not display_map or cfg.enable_cheat_map) and not (
                                levels[current_level].won
                                or levels[current_level].killed):
                            display_compass = not display_compass
                            (
                                compass_open_sound
                                if display_compass else
                                compass_close_sound
                            ).play()
                    elif event.key == pygame.K_e:
                        # Stats and map cannot be displayed together
                        if not display_map or cfg.enable_cheat_map:
                            display_stats = not display_stats
                    elif event.key in (pygame.K_LEFTBRACKET,
                                       pygame.K_RIGHTBRACKET):
                        if (event.key == pygame.K_LEFTBRACKET
                                and current_level > 0):
                            current_level -= 1
                        elif (event.key == pygame.K_RIGHTBRACKET
                                and current_level < len(levels) - 1):
                            current_level += 1
                        else:
                            continue
                        pygame.display.set_caption(
                            f"Maze - Level {current_level + 1}"
                        )
                    elif (event.key == pygame.K_q
                            and player_walls[current_level] is None
                            and wall_place_cooldown[current_level] == 0
                            and has_started_level[current_level]):
                        cardinal_facing = (
                            round(facing_directions[current_level][0]),
                            round(facing_directions[current_level][1])
                        )
                        grid_coords = level.floor_coordinates(
                            levels[current_level].player_coords
                        )
                        target = (
                            grid_coords[0] + cardinal_facing[0],
                            grid_coords[1] + cardinal_facing[1]
                        )
                        if (levels[current_level].is_coord_in_bounds(target)
                                and not levels[current_level][
                                    target, level.PRESENCE]
                                and not levels[current_level][
                                    target, level.PLAYER_COLLIDE]
                                and not levels[current_level][
                                    target, level.MONSTER_COLLIDE]):
                            player_walls[current_level] = (
                                target[0], target[1],
                                time_scores[current_level]
                            )
                            levels[current_level][
                                target, level.PRESENCE] = True
                            levels[current_level][
                                target, level.PLAYER_COLLIDE] = True
                            levels[current_level][
                                target, level.MONSTER_COLLIDE] = True
                            random.choice(wall_place_sounds).play()
                    elif event.key == pygame.K_t and has_gun[current_level]:
                        if (not display_map or cfg.enable_cheat_map) and not (
                                levels[current_level].won
                                or levels[current_level].killed):
                            has_gun[current_level] = False
                            _, hit_sprites = raycasting.get_first_collision(
                                levels[current_level],
                                facing_directions[current_level],
                                cfg.draw_maze_edge_as_wall
                            )
                            for sprite in hit_sprites:
                                if sprite.type == raycasting.MONSTER:
                                    # Monster was hit by gun
                                    levels[current_level].monster_coords = None
                                    break
                            gunshot_sound.play()
                    elif event.key in (pygame.K_r, pygame.K_ESCAPE):
                        is_reset_prompt_shown = True
                    elif event.key == pygame.K_SPACE:
                        pressed = pygame.key.get_pressed()
                        if pressed[pygame.K_RCTRL] or pressed[pygame.K_LCTRL]:
                            display_rays = not display_rays
                        else:
                            if not (levels[current_level].won
                                    or levels[current_level].killed):
                                display_map = not display_map
                                (
                                    map_open_sound
                                    if display_map else
                                    map_close_sound
                                ).play()
                    elif event.key == pygame.K_SLASH:
                        pressed = pygame.key.get_pressed()
                        if pressed[pygame.K_RCTRL] or pressed[pygame.K_LCTRL]:
                            # Launch config editor in separate thread to
                            # prevent blocking the main game.
                            threading.Thread(
                                target=config_editor.ConfigEditorApp
                            ).start()
                else:
                    if event.key == pygame.K_y:
                        # Resets almost all attributes related to the current
                        # level. Position, direction, monster, compass, etc.
                        is_reset_prompt_shown = False
                        levels[current_level].reset()
                        facing_directions[current_level] = (0.0, 1.0)
                        camera_planes[current_level] = (
                            -cfg.display_fov / 100, 0.0
                        )
                        monster_timeouts[current_level] = 0.0
                        monster_spotted[current_level] = (
                            cfg.monster_spot_timeout
                        )
                        monster_escape_clicks[current_level] = -1
                        monster_escape_time[current_level] = (
                            cfg.monster_time_to_escape
                        )
                        compass_times[current_level] = cfg.compass_time
                        compass_burned_out[current_level] = False
                        flicker_time_remaining[current_level] = 0.0
                        time_scores[current_level] = 0.0
                        move_scores[current_level] = 0.0
                        has_gun[current_level] = False
                        has_started_level[current_level] = False
                        if current_level < len(
                                screen_drawing.total_time_on_screen):
                            screen_drawing.total_time_on_screen[
                                current_level
                            ] = 0.0
                        if current_level < len(
                                screen_drawing.victory_sounds_played):
                            screen_drawing.victory_sounds_played[
                                current_level
                            ] = 0
                        display_compass = False
                        if not cfg.enable_cheat_map:
                            display_map = False
                        current_player_wall = player_walls[current_level]
                        if current_player_wall is not None:
                            levels[current_level][
                                current_player_wall[:2], level.PRESENCE
                            ] = None
                            levels[current_level][
                                current_player_wall[:2], level.PLAYER_COLLIDE
                            ] = False
                            levels[current_level][
                                current_player_wall[:2], level.MONSTER_COLLIDE
                            ] = False
                            player_walls[current_level] = None
                        wall_place_cooldown[current_level] = 0.0
                    elif event.key == pygame.K_n:
                        is_reset_prompt_shown = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mouse_coords = pygame.mouse.get_pos()
                if (mouse_coords[0] <= cfg.viewport_width
                        and event.button == pygame.BUTTON_LEFT):
                    enable_mouse_control = not enable_mouse_control
                    if enable_mouse_control:
                        pygame.mouse.set_pos(
                            (cfg.viewport_width // 2, cfg.viewport_height // 2)
                        )
                        old_mouse_pos = (
                            cfg.viewport_width // 2, cfg.viewport_height // 2
                        )
                    # Hide cursor and confine to window if controlling with
                    # mouse
                    pygame.mouse.set_visible(not enable_mouse_control)
                    pygame.event.set_grab(enable_mouse_control)
            elif (event.type == pygame.MOUSEMOTION and enable_mouse_control
                    and (not display_map or cfg.enable_cheat_map)
                    and not is_reset_prompt_shown):
                mouse_coords = pygame.mouse.get_pos()
                # How far the mouse has actually moved since the last frame.
                relative_pos = (
                    old_mouse_pos[0] - mouse_coords[0],
                    old_mouse_pos[1] - mouse_coords[1]
                )
                # Wrap mouse around screen edges
                if mouse_coords[0] == 0:
                    pygame.mouse.set_pos(
                        (cfg.viewport_width - 2, mouse_coords[1])
                    )
                elif mouse_coords[0] >= cfg.viewport_width - 1:
                    pygame.mouse.set_pos((1, mouse_coords[1]))
                # 0.0025 multiplier makes mouse speed more sensible while still
                # using the same turn speed multiplier as the keyboard.
                turn_speed_mod = cfg.turn_speed * -relative_pos[0] * 0.0025
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
                old_mouse_pos = pygame.mouse.get_pos()

        target_screen_size = (
            # Window must be at least 500×500
            max(
                cfg.viewport_width *
                (2 if cfg.enable_cheat_map and display_map else 1), 500
            ),
            max(cfg.viewport_height, 500)
        )
        if (screen.get_size()[0] != target_screen_size[0]
                or screen.get_size()[1] != target_screen_size[1]):
            screen = pygame.display.set_mode(target_screen_size)

        old_position = levels[current_level].player_coords
        # Do not allow the player to move while the map is open if cheat map is
        # not enabled — or if the reset prompt is open.
        if ((cfg.enable_cheat_map or not display_map)
                and not is_reset_prompt_shown
                and monster_escape_clicks[current_level] == -1):
            # Held down keys — movement and turning
            pressed_keys = pygame.key.get_pressed()
            move_multiplier = 1.0
            if pressed_keys[pygame.K_RCTRL] or pressed_keys[pygame.K_LCTRL]:
                move_multiplier *= cfg.crawl_multiplier
            if pressed_keys[pygame.K_RSHIFT] or pressed_keys[pygame.K_LSHIFT]:
                move_multiplier *= cfg.run_multiplier
            # Ensure framerate does not affect speed values
            turn_speed_mod = frame_time * cfg.turn_speed
            move_speed_mod = frame_time * cfg.move_speed
            # A set of events that occurred due to player movement
            events: Set[int] = set()
            if pressed_keys[pygame.K_w] or pressed_keys[pygame.K_UP]:
                if (not levels[current_level].won
                        and not levels[current_level].killed):
                    events.update(levels[current_level].move_player((
                        facing_directions[current_level][0] * move_speed_mod
                        * move_multiplier,
                        facing_directions[current_level][1] * move_speed_mod
                        * move_multiplier
                    ), has_gun[current_level], True, cfg.enable_collision))
                    has_started_level[current_level] = True
            if pressed_keys[pygame.K_s] or pressed_keys[pygame.K_DOWN]:
                if (not levels[current_level].won
                        and not levels[current_level].killed):
                    events.update(levels[current_level].move_player((
                        -facing_directions[current_level][0] * move_speed_mod
                        * move_multiplier,
                        -facing_directions[current_level][1] * move_speed_mod
                        * move_multiplier
                    ), has_gun[current_level], True, cfg.enable_collision))
                    has_started_level[current_level] = True
            if pressed_keys[pygame.K_a]:
                if (not levels[current_level].won
                        and not levels[current_level].killed):
                    events.update(levels[current_level].move_player((
                        facing_directions[current_level][1] * move_speed_mod
                        * move_multiplier,
                        -facing_directions[current_level][0] * move_speed_mod
                        * move_multiplier
                    ), has_gun[current_level], True, cfg.enable_collision))
                    has_started_level[current_level] = True
            if pressed_keys[pygame.K_d]:
                if (not levels[current_level].won
                        and not levels[current_level].killed):
                    events.update(levels[current_level].move_player((
                        -facing_directions[current_level][1] * move_speed_mod
                        * move_multiplier,
                        facing_directions[current_level][0] * move_speed_mod
                        * move_multiplier
                    ), has_gun[current_level], True, cfg.enable_collision))
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
            if level.PICKUP in events:
                pickup_flash_time_remaining = 0.4
            if level.PICKED_UP_KEY in events:
                random.choice(key_pickup_sounds).play()
            if level.PICKED_UP_KEY_SENSOR in events:
                key_sensor_times[current_level] = cfg.key_sensor_time
                key_sensor_pickup_sound.play()
            if level.PICKED_UP_GUN in events:
                has_gun[current_level] = True
                gun_pickup_sound.play()
            old_move_score = move_scores[current_level]
            move_scores[current_level] += math.sqrt(
                raycasting.no_sqrt_coord_distance(
                    old_position, levels[current_level].player_coords
                )
            )
            # Play footstep sound every time move score crosses every other
            # integer boundary.
            if move_scores[current_level] // 2 > old_move_score // 2:
                random.choice(footstep_sounds).play()
            if level.MONSTER_CAUGHT in events and cfg.enable_monster_killing:
                monster_escape_clicks[current_level] = 0
                display_map = False

        # Victory screen
        if levels[current_level].won:
            if not audio_error_occurred and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            # Overwrite existing highscores if required
            highscores_updated = False
            if (time_scores[current_level] < highscores[current_level][0]
                    or highscores[current_level][0] == 0):
                highscores[current_level] = (
                    time_scores[current_level], highscores[current_level][1]
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
            screen_drawing.draw_victory_screen(
                screen, cfg, last_level_frame[current_level],
                highscores, current_level, time_scores[current_level],
                move_scores[current_level], frame_time
            )
        # Death screen
        elif levels[current_level].killed:
            if not audio_error_occurred and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            if cfg.monster_sound_on_kill and has_started_level[current_level]:
                monster_jumpscare_sound.play()
                has_started_level[current_level] = False
            screen_drawing.draw_kill_screen(
                screen, cfg, jumpscare_monster_texture
            )
        # Currently playing
        elif not is_reset_prompt_shown:
            if not audio_error_occurred and not pygame.mixer.music.get_busy():
                pygame.mixer.music.play()
            if has_started_level[current_level]:
                # Progress time-based attributes and events
                time_scores[current_level] += frame_time
                monster_timeouts[current_level] += frame_time
                if (monster_spotted[current_level]
                        < cfg.monster_spot_timeout):
                    # Increment time since the monster was last spotted
                    monster_spotted[current_level] += frame_time
                    if (monster_spotted[current_level]
                            > cfg.monster_spot_timeout):
                        monster_spotted[current_level] = (
                            cfg.monster_spot_timeout
                        )
                if key_sensor_times[current_level] > 0:
                    key_sensor_times[current_level] -= frame_time
                    key_sensor_times[current_level] = max(
                        0.0, key_sensor_times[current_level]
                    )
                if wall_place_cooldown[current_level] > 0:
                    wall_place_cooldown[current_level] -= frame_time
                    wall_place_cooldown[current_level] = max(
                        0.0, wall_place_cooldown[current_level]
                    )
                current_player_wall = player_walls[current_level]
                if (current_player_wall is not None
                        and time_scores[current_level]
                        >= current_player_wall[2] + cfg.player_wall_time):
                    # Remove player placed wall if enough time has passed
                    levels[current_level][
                        current_player_wall[:2], level.PRESENCE
                    ] = None
                    levels[current_level][
                        current_player_wall[:2], level.PLAYER_COLLIDE
                    ] = False
                    levels[current_level][
                        current_player_wall[:2], level.MONSTER_COLLIDE
                    ] = False
                    player_walls[current_level] = None
                    wall_place_cooldown[current_level] = (
                        cfg.player_wall_cooldown
                    )
                if (display_compass and not compass_burned_out[current_level]
                        and levels[current_level].monster_coords is not None):
                    # Decay remaining compass time
                    compass_charge_delays[current_level] = (
                        cfg.compass_charge_delay
                    )
                    compass_times[current_level] -= frame_time
                    if compass_times[current_level] <= 0.0:
                        compass_times[current_level] = 0.0
                        compass_burned_out[current_level] = True
                elif compass_times[current_level] < cfg.compass_time:
                    # Compass recharging
                    if (compass_charge_delays[current_level] == 0.0
                            or compass_burned_out[current_level]):
                        multiplier = 1 / (
                            cfg.compass_charge_burn_multiplier
                            if compass_burned_out[current_level] else
                            cfg.compass_charge_norm_multiplier
                        )
                        compass_times[current_level] += frame_time * multiplier
                        if compass_times[current_level] >= cfg.compass_time:
                            compass_times[current_level] = cfg.compass_time
                            compass_burned_out[current_level] = False
                    elif compass_charge_delays[current_level] > 0.0:
                        # Decrement delay before charging the compass
                        compass_charge_delays[current_level] -= frame_time
                        compass_charge_delays[current_level] = max(
                            0.0, compass_charge_delays[current_level]
                        )
                monster_wait = levels[current_level].monster_wait
                # Move monster if it is enabled and enough time has passed
                # since last move/level start.
                if (cfg.monster_enabled and monster_wait is not None
                        and time_scores[current_level] > (
                            monster_wait
                            if cfg.monster_start_override is None else
                            cfg.monster_start_override
                        )
                        and monster_timeouts[current_level]
                        > cfg.monster_movement_wait
                        and monster_escape_clicks[current_level] == -1):
                    if (levels[current_level].move_monster()
                            and cfg.enable_monster_killing):
                        monster_escape_clicks[current_level] = 0
                        display_map = False
                    monster_timeouts[current_level] = 0
                    monster_coords = levels[current_level].monster_coords
                    if (monster_coords is not None
                            and cfg.monster_flicker_lights
                            and flicker_time_remaining[current_level] <= 0):
                        flicker_time_remaining[current_level] = 0.0
                        distance = raycasting.no_sqrt_coord_distance(
                            levels[current_level].player_coords,
                            monster_coords
                        )
                        # Flicker on every monster movement when close.
                        # Also don't divide by anything less than 1, it will
                        # have no more effect than just 1.
                        distance = max(1.0, distance - 10)
                        # < 1 exponent makes probability decay less with
                        # distance
                        if random.random() < 1 / distance ** 0.6:
                            flicker_time_remaining[current_level] = (
                                random.uniform(0.0, 0.5)
                            )
                            light_flicker_sound.play()

            # Play background breathing if the previous breathing play has
            # finished
            if time_to_breathing_finish > 0:
                time_to_breathing_finish -= frame_time
            if (time_to_breathing_finish <= 0
                    and has_started_level[current_level]):
                # There is no monster, so play the calmest breathing sound
                selected_sound = breathing_sounds[max(breathing_sounds)]
                monster_coords = levels[current_level].monster_coords
                if monster_coords is not None:
                    distance = math.sqrt(raycasting.no_sqrt_coord_distance(
                        levels[current_level].player_coords, monster_coords
                    ))
                    for min_distance, sound in breathing_sounds.items():
                        if distance >= min_distance:
                            selected_sound = sound
                        else:
                            break
                time_to_breathing_finish = selected_sound.get_length()
                selected_sound.play()

            # Play monster roaming sound if enough time has passed and
            # monster is present.
            if time_to_next_roam_sound > 0:
                time_to_next_roam_sound -= frame_time
            monster_coords = levels[current_level].monster_coords
            if (time_to_next_roam_sound <= 0
                    and monster_coords is not None
                    and monster_escape_clicks[current_level] == -1
                    and cfg.monster_sound_roaming):
                selected_sound = random.choice(monster_roam_sounds)
                time_to_next_roam_sound = (
                        selected_sound.get_length()
                        + cfg.monster_roam_sound_delay
                )
                distance = math.sqrt(raycasting.no_sqrt_coord_distance(
                    levels[current_level].player_coords, monster_coords
                ))
                # Adjust volume based on monster distance
                # (the further away the quieter) — tanh limits values
                # between 0 and 1.
                selected_sound.set_volume(math.tanh(3 / distance))
                selected_sound.play()

            if not display_map or cfg.enable_cheat_map:
                screen_drawing.draw_solid_background(screen, cfg)

            if (cfg.sky_textures_enabled
                    and (not display_map or cfg.enable_cheat_map)):
                screen_drawing.draw_sky_texture(
                    screen, cfg, facing_directions[current_level],
                    camera_planes[current_level], sky_texture
                )

            if not display_map or cfg.enable_cheat_map:
                columns, sprites = raycasting.get_columns_sprites(
                    cfg.display_columns, levels[current_level],
                    cfg.draw_maze_edge_as_wall,
                    facing_directions[current_level],
                    camera_planes[current_level]
                )
            else:
                # Skip maze rendering if map is open as it will be obscuring
                # entire viewport anyway.
                columns = []
                sprites = []
            # A combination of both wall columns and sprites
            objects: List[raycasting.Collision] = (
                columns + sprites  # type: ignore
            )
            # Draw further away objects first so that closer walls obstruct
            # sprites behind them.
            objects.sort(key=lambda x: x.euclidean_squared, reverse=True)
            # Used for displaying rays on cheat map, not used in rendering.
            ray_end_coords: List[Tuple[float, float]] = []
            for collision_object in objects:
                if isinstance(collision_object, raycasting.SpriteCollision):
                    # Sprites are just flat images scaled and blitted onto the
                    # 3D view.
                    if collision_object.type == raycasting.DECORATION:
                        try:
                            selected_sprite = decoration_textures[
                                levels[current_level].decorations[
                                    collision_object.tile
                                ]
                            ]
                        except KeyError:
                            selected_sprite = placeholder_texture
                    else:
                        try:
                            selected_sprite = sprite_textures[
                                collision_object.type
                            ]
                        except KeyError:
                            selected_sprite = placeholder_texture
                    screen_drawing.draw_sprite(
                        screen, cfg, collision_object.coordinate,
                        levels[current_level].player_coords,
                        camera_planes[current_level],
                        facing_directions[current_level], selected_sprite
                    )
                    if collision_object.type == raycasting.MONSTER:
                        # If the monster has been rendered, play the jumpscare
                        # sound if enough time has passed since the last play.
                        # Also set the timer to 0 to reset it.
                        if (cfg.monster_sound_on_spot and
                                monster_spotted[current_level]
                                == cfg.monster_spot_timeout):
                            monster_spotted_sound.play()
                        monster_spotted[current_level] = 0.0
                elif isinstance(collision_object, raycasting.WallCollision):
                    # A column is a portion of a wall that was hit by a ray.
                    side_was_ns = collision_object.side in (
                        raycasting.NORTH, raycasting.SOUTH
                    )
                    # Edge of maze when drawing maze edges as walls is disabled
                    # The entire ray will be skipped, revealing the horizon.
                    if collision_object.draw_distance == float('inf'):
                        continue
                    if display_rays:
                        # For cheat map only
                        ray_end_coords.append(collision_object.coordinate)
                    # Prevent division by 0
                    distance = max(1e-5, collision_object.draw_distance)
                    # An illusion of distance is achieved by drawing lines at
                    # different heights depending on the distance a ray
                    # travelled.
                    column_height = round(cfg.viewport_height / distance)
                    # If a texture for the current level has been found or not.
                    if cfg.textures_enabled:
                        current_player_wall = player_walls[current_level]
                        if (current_player_wall is not None
                                and collision_object.tile
                                == current_player_wall[:2]):
                            # Select appropriate player wall texture depending
                            # on how long the wall has left until breaking.
                            both_textures = player_wall_textures[
                                (
                                    (
                                        time_scores[current_level]
                                        - current_player_wall[2]
                                    ) / cfg.player_wall_time * len(
                                        player_wall_textures
                                    )
                                ).__trunc__()
                            ]
                        elif levels[current_level].is_coord_in_bounds(
                                collision_object.tile):
                            point = levels[current_level][
                                collision_object.tile, level.PRESENCE
                            ]
                            if isinstance(point, tuple):
                                texture_name = point[collision_object.side]
                            else:
                                # This should logically never happen,
                                # but just in case — default to edge texture.
                                texture_name = levels[
                                    current_level
                                ].edge_wall_texture_name
                            try:
                                both_textures = wall_textures[texture_name]
                            except KeyError:
                                both_textures = wall_textures["placeholder"]
                        else:
                            # Maze edge was hit and we should render maze edges
                            # as walls at this point.
                            try:
                                both_textures = wall_textures[
                                    levels[
                                        current_level
                                    ].edge_wall_texture_name
                                ]
                            except KeyError:
                                both_textures = wall_textures["placeholder"]
                        # Select either light or dark texture
                        # depending on side
                        texture = both_textures[int(side_was_ns)]
                        screen_drawing.draw_textured_column(
                            screen, cfg, collision_object.coordinate,
                            side_was_ns, column_height,
                            collision_object.index,
                            facing_directions[current_level], texture,
                            camera_planes[current_level]
                        )
                    else:
                        screen_drawing.draw_untextured_column(
                            screen, cfg, collision_object.index, side_was_ns,
                            column_height
                        )
            if display_map:
                current_player_wall = player_walls[current_level]
                screen_drawing.draw_map(
                    screen, cfg, levels[current_level], display_rays,
                    ray_end_coords, facing_directions[current_level],
                    key_sensor_times[current_level] > 0,
                    None
                    if current_player_wall is None else
                    current_player_wall[:2]
                )

            if pickup_flash_time_remaining > 0:
                screen_drawing.flash_viewport(
                    screen, cfg, False, pickup_flash_time_remaining
                )
                pickup_flash_time_remaining -= frame_time
                pickup_flash_time_remaining = max(
                    0.0, pickup_flash_time_remaining
                )

            monster_coords = levels[current_level].monster_coords
            if (monster_coords is not None
                    and (not display_map or cfg.enable_cheat_map)):
                # Darken viewport intermittently based on monster distance
                if cfg.monster_flicker_lights:
                    if flicker_time_remaining[current_level] > 0:
                        screen_drawing.flash_viewport(screen, cfg, True, 0.5)
                        flicker_time_remaining[current_level] -= frame_time
                        flicker_time_remaining[current_level] = max(
                            0.0, flicker_time_remaining[current_level]
                        )

            if has_gun[current_level] and (
                    not display_map or cfg.enable_cheat_map):
                screen_drawing.draw_gun(screen, cfg, first_person_gun)

            if display_compass and (not display_map or cfg.enable_cheat_map):
                monster_coords = levels[current_level].monster_coords
                if monster_coords is not None:
                    compass_target: Optional[Tuple[float, float]] = (
                        monster_coords[0] + 0.5, monster_coords[1] + 0.5
                    )
                else:
                    compass_target = None
                screen_drawing.draw_compass(
                    screen, cfg, compass_target,
                    levels[current_level].player_coords,
                    facing_directions[current_level],
                    compass_burned_out[current_level],
                    compass_times[current_level]
                )

            if display_stats and (not display_map or cfg.enable_cheat_map):
                time_score = (
                    time_scores[current_level]
                    if has_started_level[current_level] else
                    highscores[current_level][0]
                )
                move_score = (
                    move_scores[current_level]
                    if has_started_level[current_level] else
                    highscores[current_level][1]
                )
                current_player_wall = player_walls[current_level]
                screen_drawing.draw_stats(
                    screen, cfg,
                    levels[current_level].monster_coords is not None,
                    time_score, move_score,
                    len(levels[current_level].original_exit_keys)
                    - len(levels[current_level].exit_keys),
                    len(levels[current_level].original_exit_keys),
                    hud_icons, blank_icon,
                    key_sensor_times[current_level],
                    compass_times[current_level],
                    compass_burned_out[current_level],
                    None
                    if current_player_wall is None else
                    current_player_wall[2],
                    wall_place_cooldown[current_level],
                    time_scores[current_level], has_gun[current_level]
                )

            if monster_escape_clicks[current_level] >= 0:
                screen_drawing.draw_escape_screen(
                    screen, cfg, jumpscare_monster_texture
                )
                monster_escape_time[current_level] -= frame_time
                if monster_escape_time[current_level] <= 0:
                    levels[current_level].killed = True

            last_level_frame[current_level] = screen.copy()

        if is_reset_prompt_shown:
            if not audio_error_occurred and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            screen_drawing.draw_reset_prompt(
                screen, cfg, last_level_frame[current_level]
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
        pygame.display.update()


class EmptySound:
    """
    A sound to be assigned to a variable in the event that an audio error
    occurs.
    """
    @staticmethod
    def play() -> None:
        """
        Does nothing. Used to prevent error when trying to play sound after an
        audio error occurred.
        """
        pass

    @staticmethod
    def get_length() -> float:
        """
        Always returns 0.0.
        """
        return 0.0

    @staticmethod
    def set_volume(_: float) -> None:
        """
        Does nothing.
        """
        pass


if __name__ == "__main__":
    maze_game(process_command_args=True)
