from collections import defaultdict
import random

import a
from a.pommerman.envs import utility

import numpy as np


class TestAgent(a.agents.Agent):
    """This is a TestAgent. It is not meant to be submitted as playable.

    To do that, you would need to turn it into a DockerAgent. See the Docker folder for an example.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep track of recently visited uninteresting positions so that we don't keep visiting the same places.
        self._recently_visited_positions = []
        self._recently_visited_length = 6

    def act(self, obs, action_space, debug=True):
        my_position = obs['position']
        board = obs['board']
        bombs = obs['bombs']
        enemies = obs['enemies']
        ammo = obs['ammo']
        blast_strength = obs['blast_strength']
        items, dist, prev = self._djikstra(board, my_position, bombs, enemies)

        # Move if we are in an unsafe place.
        unsafe_directions = self._directions_in_range_of_bomb(board, my_position, bombs, dist)
        if unsafe_directions:
            directions = self._find_safe_directions(board, my_position, unsafe_directions, bombs, enemies)
            return random.choice(directions).value

        # Lay pomme if we are adjacent to an enemy.
        if self._is_adjacent_enemy(items, dist, enemies) and self._maybe_bomb(ammo, blast_strength, items, dist, my_position):
            return utility.Action.Bomb.value

        # Move towards an enemy if there is one in exactly three reachable spaces.
        direction = self._near_enemy(my_position, items, dist, prev, enemies, 3)
        if direction is not None:
            return direction.value

        # Move towards a good item if there is one within two reachable spaces.
        direction = self._near_item(my_position, items, dist, prev, 2)
        if direction is not None:
            return direction.value

        # Maybe lay a bomb if we are within a space of a wooden wall.
        if self._near_wood(my_position, items, dist, prev, 1):
            if self._maybe_bomb(ammo, blast_strength, items, dist, my_position):
                return utility.Action.Bomb.value
            else:
                return utility.Action.Stop.value

        # Move towards a wooden wall if there is one within two reachable spaces and you have a bomb.
        direction = self._near_wood(my_position, items, dist, prev, 2)
        if direction is not None:
            directions = self._filter_unsafe_directions(board, my_position, [direction], bombs)
            if directions:
                return directions[0].value

        # # Sometimes randomly lay a bomb.
        # if self._maybe_bomb(ammo, blast_strength, items, dist, my_position) and random.rand() < .1:
        #     return utility.Action.Bomb.value

        # Choose a random but valid direction.
        directions = [utility.Action.Stop, utility.Action.Left, utility.Action.Right, utility.Action.Up, utility.Action.Down]
        valid_directions = self._filter_invalid_directions(board, my_position, directions, enemies)
        directions = self._filter_unsafe_directions(board, my_position, valid_directions, bombs)
        directions = self._filter_recently_visited(directions, my_position, self._recently_visited_positions)
        if len(directions) > 1:
            directions = [k for k in directions if k != utility.Action.Stop]
        if not len(directions):
            directions = [utility.Action.Stop]

        # Add this position to the recently visited uninteresting positions so we don't return immediately.
        self._recently_visited_positions.append(my_position)
        self._recently_visited_positions = self._recently_visited_positions[-self._recently_visited_length:]

        return random.choice(directions).value

    @staticmethod
    def _djikstra(board, my_position, bombs, enemies):
        items = defaultdict(list)
        dist = {}
        prev = {}
        Q = []

        for r in range(len(board)):
            for c in range(len(board[0])):
                position = (r, c)
                if board[position] != utility.Item.Fog.value:
                    dist[position] = np.inf
                    prev[position] = None
                    Q.append(position)

        dist[my_position] = 0
        for bomb in bombs:
            if bomb['position'] == my_position:
                items[utility.Item.Bomb].append(my_position)

        while Q:
            Q = sorted(Q, key=lambda position: dist[position])

            position = Q.pop(0)
            if utility.position_is_passable(board, position, enemies):
                x, y = position
                val = dist[(x, y)] + 1
                for row, col in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    new_position = (row + x, col + y)
                    if not utility.position_on_board(board, new_position) or utility.position_is_fog(board, new_position):
                        continue

                    if val < dist[new_position]:
                        dist[new_position] = val
                        prev[new_position] = position

            item = utility.Item(board[position])
            items[item].append(position)

        return items, dist, prev

    def _directions_in_range_of_bomb(self, board, my_position, bombs, dist):
        ret = []

        x, y = my_position
        for bomb in bombs:
            position = bomb['position']
            distance = dist.get(position)
            if distance is None:
                continue

            bomb_range = bomb['blast_strength']
            if distance > bomb_range:
                continue

            if my_position == position:
                # We are on a bomb. All directions are in range of bomb.
                return [
                    utility.Action.Right,
                    utility.Action.Left,
                    utility.Action.Up,
                    utility.Action.Down,
                ]
            elif x == position[0]:
                if y < position[1]:
                    # Bomb is right.
                    ret.append(utility.Action.Right)
                else:
                    # Bomb is left.
                    ret.append(utility.Action.Left)
            elif y == position[1]:
                if x < position[0]:
                    # Bomb is down.
                    ret.append(utility.Action.Down)
                else:
                    # Bomb is down.
                    ret.append(utility.Action.Up)

        return list(set(ret))

    def _find_safe_directions(self, board, my_position, unsafe_directions, bombs, enemies):
        # All directions are unsafe. Return a position that won't leave us locked.
        safe = []
        bomb_range = 3 # TODO: We have hte info to make this more exact...

        if len(unsafe_directions) == 4:
            next_board = board.copy()
            next_board[my_position] = utility.Item.Bomb.value

            for direction in unsafe_directions:
                next_position = utility.get_next_position(my_position, direction)
                nx, ny = next_position
                if not utility.position_on_board(next_board, next_position) or \
                   not utility.position_is_passable(next_board, next_position, enemies):
                    continue

                is_stuck = True
                next_items, next_dist, next_prev = self._djikstra(next_board, next_position, bombs, enemies)
                for passage_position in next_items.get(utility.Item.Passage):
                    position_dist = next_dist[passage_position]
                    if position_dist == np.inf:
                        continue

                    if position_dist > bomb_range:
                        is_stuck = False
                        break

                    px, py = passage_position
                    if nx != px and ny != py:
                        is_stuck = False
                        break

                if not is_stuck:
                    safe.append(direction)
            if not safe:
                safe = [utility.Action.Stop]
            return safe
        
        x, y = my_position
        disallowed = [] # The directions that will go off the board.

        for row, col in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            position = (x + row, y + col)
            direction = utility.get_direction(my_position, position)

            # Don't include any direction that will go off of the board.
            if not utility.position_on_board(board, position):
                disallowed.append(direction)
                continue

            # Don't include any direction that we know is unsafe.
            if direction in unsafe_directions:
                continue

            if utility.position_is_passable(board, position, enemies) or utility.position_is_fog(board, position):
                safe.append(direction)

        if not safe:
            # We don't have any safe directions, so return something that is allowed.
            safe = [k for k in unsafe_directions if k not in disallowed]

        if not safe:
            # We don't have ANY directions. So return the stop choice.
            return [utility.Action.Stop]

        return safe

    @staticmethod
    def _is_adjacent_enemy(items, dist, enemies):
        for enemy in enemies:
            for position in items.get(enemy, []):
                if dist[position] == 1:
                    return True
        return False

    @staticmethod
    def _has_bomb(obs):
        return obs['ammo'] >= 1

    @staticmethod
    def _maybe_bomb(ammo, blast_strength, items, dist, my_position):
        """Returns whether we can safely bomb right now.

        Decides this based on:
        1. Do we have ammo?
        2. If we laid a bomb right now, will we be stuck?
        """
        # Do we have ammo?
        if ammo < 1:
            return False

        # Will we be stuck?
        x, y = my_position
        for position in items.get(utility.Item.Passage):
            if dist[position] == np.inf:
                continue

            # We can reach a passage that's outside of the bomb strength.
            if dist[position] > blast_strength:
                return True

            # We can reach a passage that's outside of the bomb scope.
            px, py = position
            if px != x and py != y:
                return True

        return False

    @staticmethod
    def _nearest_position(dist, objs, items, radius, exact=False):
        nearest = None
        dist_to = max(dist.values())

        for obj in objs:
            for position in items.get(obj, []):
                d = dist[position]
                if exact and d == radius:
                    return position

                if d <= radius and d <= dist_to:
                    nearest = position
                    dist_to = d

        if exact and dist_to != radius:
            nearest = None
        return nearest

    @staticmethod
    def _get_direction_towards_position(my_position, position, prev):
        if not position:
            return None

        next_position = position
        while prev[next_position] != my_position:
            next_position = prev[next_position]

        return utility.get_direction(my_position, next_position)

    @classmethod
    def _near_enemy(cls, my_position, items, dist, prev, enemies, radius):
        nearest_enemy_position = cls._nearest_position(dist, enemies, items, radius, exact=True)
        return cls._get_direction_towards_position(my_position, nearest_enemy_position, prev)

    @classmethod
    def _near_item(cls, my_position, items, dist, prev, radius):
        objs = [
            utility.Item.ExtraBomb,
            utility.Item.IncrRange,
            utility.Item.Kick
        ]
        nearest_item_position = cls._nearest_position(dist, objs, items, radius)
        return cls._get_direction_towards_position(my_position, nearest_item_position, prev)

    @classmethod
    def _near_wood(cls, my_position, items, dist, prev, radius):
        objs = [utility.Item.Wood]
        nearest_item_position = cls._nearest_position(dist, objs, items, radius)
        return cls._get_direction_towards_position(my_position, nearest_item_position, prev)

    @staticmethod
    def _filter_invalid_directions(board, my_position, directions, enemies):
        ret = []
        for direction in directions:
            position = utility.get_next_position(my_position, direction)
            if utility.position_on_board(board, position) and utility.position_is_passable(board, position, enemies):
                ret.append(direction)
        return ret

    @staticmethod
    def _filter_unsafe_directions(board, my_position, directions, bombs):
        ret = []
        for direction in directions:
            x, y = utility.get_next_position(my_position, direction)
            is_bad = False
            for bomb in bombs:
                bx, by = bomb['position']
                blast_strength = bomb['blast_strength']
                if (x == bx and abs(by - y) <= blast_strength) or \
                   (y == by and abs(bx - x) <= blast_strength):
                    is_bad = True
                    break
            if not is_bad:
                ret.append(direction)

        return ret

    @staticmethod
    def _filter_recently_visited(directions, my_position, recently_visited_positions):
        ret = []
        for direction in directions:
            if not utility.get_next_position(my_position, direction) in recently_visited_positions:
                ret.append(direction)

        if not ret:
            ret = directions
        return ret