from __future__ import annotations

ENEMY_CORE_SOURCE = r'''class AfterImageGhost:
    def __init__(self, x, y, w, h, base_color, ttl=AFTERIMAGE_TTL, sprite: pygame.Surface | None = None):
        self.x = int(x);
        self.y = int(y)  # 脚底世界像素
        self.w = int(w);
        self.h = int(h)
        r, g, b = base_color if base_color else (120, 220, 160)
        self.color = (int(r), int(g), int(b))
        self.ttl = float(ttl);
        self.life0 = float(ttl)
        self.sprite = sprite

    def update(self, dt):
        self.ttl -= dt
        return self.ttl > 0

    # —— Top-down：屏幕=世界−相机，按 midbottom 对齐 ——
    def draw_topdown(self, screen, cam_x, cam_y):
        if self.ttl <= 0: return
        alpha = max(0, min(255, int(255 * (self.ttl / self.life0))))
        rect = pygame.Rect(0, 0, self.w, self.h)
        rect.midbottom = (int(self.x - cam_x), int(self.y - cam_y))
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        s.fill((*self.color, alpha))
        screen.blit(s, rect.topleft)

    # —— ISO：脚底世界像素 → 世界格 → 等距投影坐标（再设 midbottom）——
    def draw_iso(self, screen, camx, camy):
        if self.ttl <= 0: return
        alpha = max(0, min(255, int(255 * (self.ttl / self.life0))))
        wx = self.x / CELL_SIZE
        wy = (self.y - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        rect = pygame.Rect(0, 0, self.w, self.h)
        rect.midbottom = (int(sx), int(sy))
        if self.sprite:
            tint = pygame.Surface(self.sprite.get_size(), pygame.SRCALPHA)
            tint.fill((*self.color, alpha))
            mask = _sprite_alpha_mask(self.sprite)
            tint.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(tint, self.sprite.get_rect(midbottom=rect.midbottom))
        else:
            s = pygame.Surface(rect.size, pygame.SRCALPHA)
            s.fill((*self.color, alpha))
            screen.blit(s, rect.topleft)

    # 兜底（仍有旧调用时，尽量别用它）
    def draw(self, screen):
        pass


class Enemy:
    def __init__(self, pos: Tuple[int, int], attack: int = ENEMY_ATTACK, speed: int = ENEMY_SPEED,
                 ztype: str = "basic", hp: Optional[int] = None):
        self.x = pos[0] * CELL_SIZE
        self.y = pos[1] * CELL_SIZE
        self._vx = 0.0
        self._vy = 0.0
        self.attack = attack
        self.speed = speed
        # Normalize deprecated/alias types
        self.type = "fast" if ztype == "trailrunner" else ztype
        self.color = ENEMY_COLORS.get(self.type, (255, 60, 60))
        self.size_category = ENEMY_SIZE_NORMAL
        # === special type state ===
        # Suicide types start unarmed; fuse begins when near the player
        self.fuse = None
        self.suicide_armed = False
        self.buff_cd = 0.0 if ztype == "buffer" else None
        self.shield_cd = 0.0 if ztype == "shielder" else None
        self.shield_hp = 0  # 当前护盾值
        self.shield_t = 0.0  # 护盾剩余时间
        self.ranged_cd = 0.0 if ztype in ("ranged", "spitter") else None
        self.buff_t = 0.0  # 自身被增益剩余时间
        self.buff_atk_mult = 1.0
        self.buff_spd_add = 0
        self.coins_absorbed = 0
        # XP & rank
        self.z_level = 1
        self.xp = 0
        self.xp_to_next = ENEMY_XP_TO_LEVEL
        self.is_elite = False
        self.is_boss = False
        self.radius = ENEMY_RADIUS
        # ABS
        self._stuck_t = 0.0  # 被卡住累计时长
        self._avoid_t = 0.0  # 侧移剩余时间
        self._avoid_side = 1  # 侧移方向（1 或 -1）
        self._focus_block = None  # 当前决定优先破坏的可破坏物
        self._last_xy = (self.x, self.y)
        # —— 路径跟随（懒 A*）所需的轻量状态 ——
        self._path = []  # 路径里的网格路点列表（不含起点）
        self._path_step = 0  # 当前要走向的路点索引
        # Spoil
        self.spoils = 0  # 当前持有金币
        self._gold_glow_t = 0.0  # 金色拾取光晕计时器
        # D.O.T. Rounds stacks (per-enemy)
        self.dot_rounds_stacks = []
        self._dot_rounds_tick_t = float(DOT_ROUNDS_TICK_INTERVAL)
        self._dot_rounds_accum = 0.0
        self.speed = float(self.speed)  # 改成 float，支持 +0.5 的增速
        # split flags (only for splinter)
        self._can_split = (self.type == "splinter")
        self._split_done = False
        base_hp = 30 if hp is None else hp
        # type tweaks
        if ztype == "fast":
            self.speed = max(int(self.speed + 1), int(self.speed * 1.5))
            base_hp = int(base_hp * 0.7)
        if self.type == "strong":
            base_hp = int(base_hp * 1.35)
            self.attack = max(1, int(self.attack * 1.15))
        if ztype == "tank":
            self.attack = int(self.attack * 0.6)
            base_hp = int(base_hp * 1.8)
        self.hp = max(1, base_hp)
        self.max_hp = self.hp
        self._hit_flash = 0.0
        self._flash_prev_hp = int(self.hp)
        base_size = int(CELL_SIZE * 0.6)
        if self.type == "tank":
            base_size = int(CELL_SIZE * TANK_SIZE_MULT)
            self._size_override = base_size  # preserve the larger footprint when scaling
        elif self.type == "strong":
            base_size = int(CELL_SIZE * STRONG_SIZE_MULT)
            self._size_override = base_size  # keep the heavier footprint after scaling
        elif self.type == "shielder":
            base_size = int(CELL_SIZE * SHIELDER_SIZE_MULT)
            self._size_override = base_size  # preserve the bulkier footprint when scaling
        self.size = base_size
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        self.radius = int(self.size * 0.5)
        self._base_size = int(self.size)
        set_enemy_size_category(self)
        # track trailing foot points for afterimage
        self._foot_prev = (self.rect.centerx, self.rect.bottom)
        self._foot_curr = (self.rect.centerx, self.rect.bottom)
        self.spawn_delay = 0.6
        self._enrage_cd_mult = 1.0
        self._ground_spike_slow_t = 0.0
        self._paint_contact_mult = 1.0
        self.enemy_trace_timer = 0.0
        self.last_paint_pos = None
        self._hell_paint_t = 0.0
        self._hell_paint_pos = None

    def draw(self, screen):
        color = getattr(self, "_current_color", self.color)
        pygame.draw.rect(screen, color, self.rect)
        self._spawn_elapsed = 0.0

    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def gain_xp(self, amount: int):
        self.xp += int(max(0, amount))
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.z_level += 1
            self.xp_to_next = int(self.xp_to_next * 1.25 + 0.5)
            # stat bumps
            self.attack = int(self.attack * 1.08 + 1)
            self.max_hp = int(self.max_hp * 1.10 + 1)
            self.hp = min(self.max_hp, self.hp + 2)
        if not getattr(self, "is_boss", False):
            # Keep regular enemies at their intended footprint; respect type-specific overrides.
            base_override = getattr(self, "_size_override", None)
            if base_override is not None:
                base = int(base_override)
            elif getattr(self, "type", "") == "ravager":
                base = int(CELL_SIZE * RAVAGER_SIZE_MULT)
            else:
                base = int(CELL_SIZE * 0.6)  # match player footprint
            new_size = base
            if new_size != self.size:
                cx, cy = self.rect.center
                self.size = new_size
                self.rect = pygame.Rect(0, 0, self.size, self.size)
                self.rect.center = (cx, cy)
                self.x = float(self.rect.x)
                self.y = float(self.rect.y - INFO_BAR_HEIGHT)
                # 用最终矩形重置残影足点，保证轨迹贴合
                self._foot_prev = (self.rect.centerx, self.rect.bottom)
                self._foot_curr = (self.rect.centerx, self.rect.bottom)
                apply_coin_absorb_scale(self)
                set_enemy_size_category(self)

    def add_spoils(self, n: int):
        """僵尸拾取金币后的即时强化。"""
        n = int(max(0, n))
        if n <= 0:
            return
        self.coins_absorbed = int(getattr(self, "coins_absorbed", 0)) + n
        # 逐枚处理，确保跨阈值时触发攻击/速度加成
        for _ in range(n):
            self.spoils += 1
            # +HP 与 +MaxHP
            self.max_hp += Z_SPOIL_HP_PER
            self.hp = min(self.max_hp, self.hp + Z_SPOIL_HP_PER)
            # 攻击阈值
            if self.spoils % Z_SPOIL_ATK_STEP == 0:
                self.attack += 1
            # 速度阈值
            if self.spoils % Z_SPOIL_SPD_STEP == 0:
                self.speed = min(Z_SPOIL_SPD_CAP, float(self.speed) + float(Z_SPOIL_SPD_ADD))
        # coin-based scaling
        apply_coin_absorb_scale(self)
        # 触发拾取光晕
        self._gold_glow_t = float(Z_GLOW_TIME)

    # ==== 通用：把朝向向量分解到等距基向量（e1=(1,1), e2=(1,-1)）====
    @staticmethod
    def iso_chase_step(from_xy, to_xy, speed):
        fx, fy = from_xy
        tx, ty = to_xy
        vx, vy = tx - fx, ty - fy
        L = (vx * vx + vy * vy) ** 0.5 or 1.0
        ux, uy = vx / L, vy / L
        # use the same equalized speed you use for the player
        return iso_equalized_step(ux, uy, speed)

    @staticmethod
    def feet_xy(entity):
        # “脚底”坐标：用底边中心点（避免因为sprite高度导致距离判断穿帮）
        return (entity.x + entity.size * 0.5, entity.y + entity.size)

    @staticmethod
    def first_obstacle_on_grid_line(a_cell, b_cell, obstacles_dict):
        x0, y0 = a_cell;
        x1, y1 = b_cell
        dx = abs(x1 - x0);
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0);
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            ob = obstacles_dict.get((x0, y0))
            if ob: return ob
            if x0 == x1 and y0 == y1: break
            e2 = 2 * err
            if e2 >= dy: err += dy; x0 += sx
            if e2 <= dx: err += dx; y0 += sy
        return None

    def _choose_bypass_cell(self, ob_cell, player_cell, obstacles_dict):
        """Pick a simple side cell next to the blocking obstacle to go around it."""
        ox, oy = ob_cell
        px, py = player_cell
        # Prefer going around the obstacle on the side perpendicular
        # to the main player-obstacle axis (very simple wall-hug).
        if abs(px - ox) >= abs(py - oy):
            primary = [(ox, oy - 1), (ox, oy + 1)]
        else:
            primary = [(ox - 1, oy), (ox + 1, oy)]

        def free(c):
            x, y = c
            return (0 <= x < GRID_SIZE) and (0 <= y < GRID_SIZE) and (c not in obstacles_dict)

        cands = [c for c in primary if free(c)]
        if not cands:
            # Fallback: try the four diagonals
            diag = [(ox + 1, oy + 1), (ox + 1, oy - 1), (ox - 1, oy + 1), (ox - 1, oy - 1)]

            def diag_valid(c):
                cx, cy = c
                # NEW: reject diagonal if both side-adjacents are blocked (corner)
                side1 = (ox, cy) in obstacles_dict
                side2 = (cx, oy) in obstacles_dict
                return free(c) and not (side1 and side2)

            cands = [c for c in diag if free(c)]
        if not cands:
            return None
        # Choose the one closer to the player.
        return min(cands, key=lambda c: (c[0] - px) ** 2 + (c[1] - py) ** 2)

    def move_and_attack(self, player, obstacles, game_state, attack_interval=0.5, dt=1 / 60):
        # shift last → prev at frame start
        self._foot_prev = getattr(self, "_foot_curr", (self.rect.centerx, self.rect.bottom))
        frame_scale = dt * 60.0  # convert 60 FPS-tuned speeds into this frame's step
        # ---- BUFF/生成延迟/速度上限：与原逻辑一致 ----
        base_attack = self.attack
        # Hell Domain: generic attack scaler for melee/block hits/skill uses
        if getattr(game_state, "biome_active", None) == "Scorched Hell":
            base_attack = int(base_attack * (1.5 if getattr(self, "is_boss", False) else 2.0))
        base_speed = float(self.speed)
        if getattr(self, "buff_t", 0.0) > 0.0:
            base_attack = int(base_attack * getattr(self, "buff_atk_mult", 1.0))
            base_speed = float(base_speed) + float(getattr(self, "buff_spd_add", 0))
            self.buff_t = max(0.0, self.buff_t - dt)
        paint_intensity = 0.0
        if game_state is not None and hasattr(game_state, "paint_intensity_at_world"):
            paint_intensity = game_state.paint_intensity_at_world(self.rect.centerx, self.rect.centery, owner=2)
        self._paint_contact_mult = 1.0 + ENEMY_PAINT_DAMAGE_BONUS * paint_intensity
        base_speed *= (1.0 + ENEMY_PAINT_SPEED_BONUS * paint_intensity)
        base_speed *= float(getattr(self, "_hurricane_slow_mult", 1.0))
        spike_slow_t = float(getattr(self, "_ground_spike_slow_t", 0.0))
        if spike_slow_t > 0.0:
            spike_slow_t = max(0.0, spike_slow_t - dt)
            self._ground_spike_slow_t = spike_slow_t
            base_speed *= GROUND_SPIKES_SLOW_MULT
        speed = float(min(Z_SPOIL_SPD_CAP, max(0.5, base_speed)))
        is_bandit = (getattr(self, "type", "") == "bandit")
        bandit_break_t = 0.0
        bandit_wind_trapped = False
        if is_bandit:
            bandit_break_t = max(0.0, float(getattr(self, "bandit_break_t", 0.0)) - dt)
            self.bandit_break_t = bandit_break_t
            bandit_wind_trapped = bool(getattr(self, "_wind_trapped", False))
        bandit_prev_pos = getattr(self, "_bandit_last_pos", (self.x, self.y))
        if not hasattr(self, "attack_timer"): self.attack_timer = 0.0
        self.attack_timer += dt
        # Cooldown between applying contact damage to blocking destructible tiles
        self._block_contact_cd = max(0.0, float(getattr(self, "_block_contact_cd", 0.0)) - dt)
        # simple bypass lifetime
        self._bypass_t = max(0.0, getattr(self, "_bypass_t", 0.0) - dt)
        # wipe last-hit each frame (esp. when we skip collide due to no_clip)
        self._hit_ob = None
        # if our previous focus block was destroyed last frame, drop it
        if getattr(self, "_focus_block", None):
            gp = getattr(self._focus_block, "grid_pos", None)
            if (gp is not None) and (gp not in game_state.obstacles):
                self._focus_block = None
        if is_bandit:
            self.mode = getattr(self, "mode", "FLEE")
            self.last_collision_tile = getattr(self, "last_collision_tile", None)
            self.frames_on_same_tile = int(getattr(self, "frames_on_same_tile", 0))
            self.stuck_origin_pos = tuple(getattr(self, "stuck_origin_pos", (self.x, self.y)))
            esc_dir = getattr(self, "escape_dir", (0.0, 0.0))
            if not (isinstance(esc_dir, (tuple, list)) and len(esc_dir) == 2):
                esc_dir = (0.0, 0.0)
            self.escape_dir = esc_dir
            self.escape_timer = float(getattr(self, "escape_timer", 0.0))
        if is_bandit and getattr(self, "bandit_triggered", False):
            # While fleeing, never stick to a focus target or bypass side cell
            self._focus_block = None
            self._bypass_t = 0.0
            self._bypass_cell = None
        # 目标（默认追玩家；若锁定了一块挡路的可破坏物，则追它的中心）
        zx, zy = Enemy.feet_xy(self)
        px, py = player.rect.centerx, player.rect.centery
        player_move_dx, player_move_dy = getattr(player, "_last_move_vec", (0.0, 0.0))
        target_cx, target_cy = px, py
        # Distance to player (used by bandit flee logic)
        dxp = px - zx
        dyp = py - zy
        dist2_to_player = dxp * dxp + dyp * dyp
        # one-time trigger – once bandit enters flee radius, it stays in flee mode
        if is_bandit and dist2_to_player <= (BANDIT_FLEE_RADIUS * BANDIT_FLEE_RADIUS):
            # only set once
            if not getattr(self, "bandit_triggered", False):
                self.bandit_triggered = True
        bandit_flee = is_bandit and getattr(self, "bandit_triggered", False)
        if bandit_flee:
            speed *= BANDIT_FLEE_SPEED_MULT
            if bandit_break_t > 0.0:
                speed *= BANDIT_BREAK_SLOW_MULT
            # steer toward the farthest corner away from the player
            pcx = int(player.rect.centerx // CELL_SIZE)
            pcy = int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE)
            corners = [(0, 0), (0, GRID_SIZE - 1), (GRID_SIZE - 1, 0), (GRID_SIZE - 1, GRID_SIZE - 1)]
            tx, ty = max(corners, key=lambda c: (c[0] - pcx) ** 2 + (c[1] - pcy) ** 2)
            target_cx = tx * CELL_SIZE + CELL_SIZE * 0.5
            target_cy = ty * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT
            # drop any previous chase commitment when fleeing
            self._ff_commit = None
            self._ff_commit_t = 0.0
        speed_step = speed * frame_scale
        # --- Twin “lane” offset and mild separation so they don’t block each other ---
        if getattr(self, "is_boss", False) and getattr(self, "twin_id", None) is not None:
            cx0 = self.x + self.size * 0.5
            cy0 = self.y + self.size * 0.5 + INFO_BAR_HEIGHT
            # direction to player/focus target
            dxp, dyp = target_cx - cx0, target_cy - cy0
            mag = (dxp * dxp + dyp * dyp) ** 0.5 or 1.0
            nx, ny = dxp / mag, dyp / mag
            # pick a lane: perpendicular offset (left/right by slot)
            px, py = -ny, nx
            slot = float(getattr(self, "twin_slot", +1))
            lane_offset = 0.45 * CELL_SIZE * slot
            target_cx += px * lane_offset
            target_cy += py * lane_offset
            # soft separation from partner if we’re too close
            partner = None
            ref = getattr(self, "_twin_partner_ref", None)
            if callable(ref):
                partner = ref()
            if partner and getattr(partner, "hp", 1) > 0:
                pcx, pcy = partner.rect.centerx, partner.rect.centery
                ddx, ddy = cx0 - pcx, cy0 - pcy
                d2 = ddx * ddx + ddy * ddy
                too_close = (1.2 * CELL_SIZE) ** 2
                if d2 < too_close:
                    k = (too_close - d2) / too_close
                    target_cx += ddx * 0.35 * k
                    target_cy += ddy * 0.35 * k
        # 若之前撞到了可破坏物，则临时聚焦（更积极地砍）
        if getattr(self, "_hit_ob", None):
            if getattr(self, "can_crush_all_blocks", False) or getattr(self._hit_ob, "type", "") == "Destructible":
                self._focus_block = self._hit_ob
        # 视线被障碍挡住：
        # - 若是红色(Destructible) → 把它当“门”，优先破坏
        # - 否则：普通僵尸(basic) 尝试一个极简的“旁路”目标格
        if not self._focus_block:
            gz = (int((self.x + self.size * 0.5) // CELL_SIZE),
                  int((self.y + self.size * 0.5) // CELL_SIZE))
            if bandit_flee:
                gp = (int(target_cx // CELL_SIZE),
                      int((target_cy - INFO_BAR_HEIGHT) // CELL_SIZE))
            else:
                gp = (int(player.rect.centerx // CELL_SIZE),
                      int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE))  # <- use rect center
            ob = self.first_obstacle_on_grid_line(gz, gp, game_state.obstacles)
            self._focus_block = None
            if ob:
                if bandit_flee:
                    # pick a neighboring free cell of the blocking obstacle that increases distance to player
                    ox, oy = ob.grid_pos
                    free = []
                    for nx, ny in ((ox + 1, oy), (ox - 1, oy), (ox, oy + 1), (ox, oy - 1)):
                        if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE and (nx, ny) not in game_state.obstacles:
                            free.append((nx, ny))
                    if free:
                        bx, by = max(free, key=lambda c: (c[0] - pcx) ** 2 + (c[1] - pcy) ** 2)
                        self._bypass_cell = (bx, by)
                        self._bypass_t = 0.60
                elif getattr(ob, "type", "") == "Destructible":
                    # red block: break it
                    self._focus_block = ob
                elif not getattr(self, "is_boss", False):
                    # grey block: pick a side cell and follow it for a short time
                    bypass = self._choose_bypass_cell(ob.grid_pos, gp, game_state.obstacles)
                    if bypass:
                        self._bypass_cell = bypass
                        self._bypass_t = 0.50  # ~0.5s of commitment to the side cell
        if self._focus_block and not bandit_flee:
            target_cx, target_cy = self._focus_block.rect.centerx, self._focus_block.rect.centery
        fd = None  # flow-distance field; stays None if we skip FF steering (e.g., during escape override)
        escape_override = False
        if bandit_flee and getattr(self, "mode", "FLEE") == "ESCAPE_CORNER":
            ex, ey = self.escape_dir
            mag = (ex * ex + ey * ey) ** 0.5
            if mag < 1e-4:
                ex, ey = -dxp, -dyp
                mag = (ex * ex + ey * ey) ** 0.5 or 1.0
            ux, uy = ex / mag, ey / mag
            vx_des, vy_des = chase_step(ux, uy, speed_step)
            tau = 0.12
            alpha = 1.0 - pow(0.001, dt / tau)
            self._vx = (1.0 - alpha) * getattr(self, "_vx", 0.0) + alpha * vx_des
            self._vy = (1.0 - alpha) * getattr(self, "_vy", 0.0) + alpha * vy_des
            vx, vy = self._vx, self._vy
            dx, dy = vx, vy
            oldx, oldy = self.x, self.y
            escape_override = True
            self.escape_timer = max(0.0, float(getattr(self, "escape_timer", 0.0)) - dt)
            if self.escape_timer <= 0.0:
                self.mode = "FLEE"
                self.last_collision_tile = None
                self.frames_on_same_tile = 0
        if not escape_override:
            # —— 若已有“临时路径”，把目标切换到下一个路点（脚底中心） ——
            # 当前“脚底”所在格
            gx = int((self.x + self.size * 0.5) // CELL_SIZE)
            gy = int((self.y + self.size) // CELL_SIZE)
            if self._path_step < len(self._path):
                nx, ny = self._path[self._path_step]
                # 到达该格就推进
                if gx == nx and gy == ny:
                    self._path_step += 1
                    if self._path_step < len(self._path):
                        nx, ny = self._path[self._path_step]
                # 仍有路点：将追踪目标改成这个路点的“脚底”
                if self._path_step < len(self._path):
                    target_cx = nx * CELL_SIZE + CELL_SIZE * 0.5
                    target_cy = ny * CELL_SIZE + CELL_SIZE
            # === 4) FLOW-FIELD STEER (preferred) ===
            cx0, cy0 = self.rect.centerx, self.rect.centery
            gx = int(cx0 // CELL_SIZE)
            gy = int((cy0 - INFO_BAR_HEIGHT) // CELL_SIZE)
            ff = getattr(game_state, "ff_next", None)
            fd = getattr(game_state, "ff_dist", None)
            # 1) primary: read next step from the 2-D flow field
            step = ff[gx][gy] if (ff is not None and 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE) else None
            boss_simple = (getattr(self, "is_boss", False)
                           or getattr(self, "type", "") in ("boss_mist", "boss_mem"))
            if boss_simple:
                step = None  # stay on simple-chase
                self._ff_commit = None  # <-- critical: use None, not 0.0
                self._ff_commit_t = 0.0
                self._avoid_t = 0.0
            # If this is a bandit that has triggered flee mode, invert FF preference to run away
            bandit_escape_step = None
            if bandit_flee and fd is not None:
                best = None
                bestd = -1
                for nx in (gx - 1, gx, gx + 1):
                    for ny in (gy - 1, gy + 1):
                        if nx == gx and ny == gy:
                            continue
                        if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
                            continue
                        if (nx, ny) in game_state.obstacles:
                            continue
                        if nx != gx and ny != gy:
                            if (gx, ny) in game_state.obstacles or (nx, gy) in game_state.obstacles:
                                continue
                        d = fd[ny][nx]
                        if d > bestd and not Enemy.first_obstacle_on_grid_line((gx, gy), (nx, ny), game_state.obstacles):
                            bestd = d
                            best = (nx, ny)
                bandit_escape_step = best
                if bandit_escape_step is not None:
                    step = bandit_escape_step
            # 2) fallback: pick the neighbor with the smallest distance (row-major: fd[ny][nx])
            if step is None and fd is not None and not boss_simple:
                best = None
                bestd = 10 ** 9
                for nx in (gx - 1, gx, gx + 1):
                    for ny in (gy - 1, gy + 1):
                        if nx == gx and ny == gy:
                            continue
                        if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
                            continue
                        # 1) skip blocked target cells
                        if (nx, ny) in game_state.obstacles:
                            continue
                        # 2) forbid cutting corners on diagonals
                        if nx != gx and ny != gy:
                            if (gx, ny) in game_state.obstacles or (nx, gy) in game_state.obstacles:
                                continue
                        d = fd[ny][nx]
                        if d < bestd:
                            if nx != gx and ny != gy:
                                if ((gx, ny) in game_state.obstacles) and ((nx, gy) in game_state.obstacles):
                                    continue
                                # existing “no-hidden-corner” / LoS check
                            if not Enemy.first_obstacle_on_grid_line((gx, gy), (nx, ny), game_state.obstacles):
                                bestd = d
                                best = (nx, ny)
                step = best
                # --- smooth FF steering: commit briefly to avoid oscillation (applies to all) ---
                if step is not None:
                    prev = getattr(self, "_ff_commit", None)
                    # Make sure prev is a (x,y) cell, otherwise treat as no commit
                    if not (isinstance(prev, (tuple, list)) and len(prev) == 2):
                        prev = None
                    if prev is None:
                        self._ff_commit = step
                        self._ff_commit_t = 0.25
                    else:
                        if step != prev:
                            pcx = prev[0] * CELL_SIZE + CELL_SIZE * 0.5
                            pcy = prev[1] * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT
                            d2 = (pcx - cx0) ** 2 + (pcy - cy0) ** 2
                            if d2 <= (CELL_SIZE * 0.35) ** 2 or getattr(self, "_ff_commit_t", 0.0) <= 0.0:
                                self._ff_commit = step
                                self._ff_commit_t = 0.25
                            else:
                                step = prev
                        else:
                            self._ff_commit_t = max(0.0, getattr(self, "_ff_commit_t", 0.0) - dt)
                # else:
                #     # bosses take simple-chase path (ignore FF)
                #     step = step if not is_boss_simple else None
            # Simple-bypass override for regular enemies
            if getattr(self, "_bypass_t", 0.0) > 0.0 and getattr(self, "_bypass_cell", None) is not None:
                # drop it if we already reached the side cell or LoS is now clear
                if (gx, gy) == self._bypass_cell or not self.first_obstacle_on_grid_line((gx, gy), gp,
                                                                                         game_state.obstacles):
                    self._bypass_t = 0.0
                    self._bypass_cell = None
                else:
                    step = self._bypass_cell
            if step is not None:
                nx, ny = step
                # world-pixel center of the recommended next cell
                next_cx = nx * CELL_SIZE + CELL_SIZE * 0.5
                next_cy = ny * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT
                dx = next_cx - cx0
                dy = next_cy - cy0
                L = (dx * dx + dy * dy) ** 0.5 or 1.0
                ux, uy = dx / L, dy / L
                # desired velocity this frame
                vx_des, vy_des = chase_step(ux, uy, speed_step)
                # light steering smoothing (≈ 120 ms time constant)
                tau = 0.12
                alpha = 1.0 - pow(0.001, dt / tau)  # stable, dt-based lerp factor
                self._vx = (1.0 - alpha) * getattr(self, "_vx", 0.0) + alpha * vx_des
                self._vy = (1.0 - alpha) * getattr(self, "_vy", 0.0) + alpha * vy_des
                # use smoothed velocity as this frame’s step
                vx, vy = self._vx, self._vy
                dx, dy = vx, vy
                oldx, oldy = self.x, self.y
            else:
                # Fallback: keep your existing target-point chase (path step / LOS)
                dx = target_cx - cx0
                dy = target_cy - cy0
                L = (dx * dx + dy * dy) ** 0.5 or 1.0
                ux, uy = dx / L, dy / L
                # Bandit logic: once flee has triggered, always run AWAY from the player
                if bandit_flee:
                    flee_x, flee_y = -dxp, -dyp  # straight away from player
                    # if still near-zero (standing on the player), pick a perpendicular shove
                    if abs(flee_x) < 1e-4 and abs(flee_y) < 1e-4:
                        flee_x, flee_y = -dy, dx
                    mag = (flee_x * flee_x + flee_y * flee_y) ** 0.5 or 1.0
                    ux, uy = flee_x / mag, flee_y / mag
                # desired velocity this frame
                vx_des, vy_des = chase_step(ux, uy, speed_step)
                # light steering smoothing (≈ 120 ms time constant)
                tau = 0.12
                alpha = 1.0 - pow(0.001, dt / tau)  # stable, dt-based lerp factor
                self._vx = (1.0 - alpha) * getattr(self, "_vx", 0.0) + alpha * vx_des
                self._vy = (1.0 - alpha) * getattr(self, "_vy", 0.0) + alpha * vy_des
                # use smoothed velocity as this frame’s step
                vx, vy = self._vx, self._vy
                dx, dy = vx, vy
                oldx, oldy = self.x, self.y
        # If target is exactly on us this frame, dodge sideways deterministically
        if not getattr(self, "is_boss", False):
            if abs(dx) < 1e-3 and abs(dy) < 1e-3:
                slot = float(getattr(self, "twin_slot", 1.0))
                dx, dy = 0.0, slot * max(0.6, min(speed, 1.2)) * frame_scale
        # —— 侧移（反卡住）：被卡住一小会儿就沿着法向 90° 滑行 ——
        if self._avoid_t > 0.0:
            # 左右各一条切线，选择预先决定的那一边
            if self._avoid_side > 0:
                ax, ay = -dy, dx  # 向左
            else:
                ax, ay = dy, -dx  # 向右
            dx, dy = ax, ay
            self._avoid_t = max(0.0, self._avoid_t - dt)
        # Bosses: no side-slip shimmy
        if (not getattr(self, "is_boss", False)) and self._avoid_t > 0.0:
            if self._avoid_side > 0:
                ax, ay = -dy, dx
            else:
                ax, ay = dy, -dx
            dx, dy = ax, ay
            self._avoid_t = max(0.0, self._avoid_t - dt)
        # --- no-clip phase: skip collision resolution for a few frames after bulldozing
        if getattr(self, "no_clip_t", 0.0) > 0.0:
            self.no_clip_t = max(0.0, self.no_clip_t - dt)
            self.x += dx
            self.y += dy
            # sync rect and bail directly into post-move logic
            self.rect.x = int(self.x)
            self.rect.y = int(self.y + INFO_BAR_HEIGHT)
            # OPTIONAL tiny forward nudge to defeat integer clamp remnants
            if abs(dx) < 0.5 and abs(dy) < 0.5:
                self.x += 0.8 * (1 if (self.rect.centerx < player.rect.centerx) else -1)
            goto_post_move = True
        else:
            goto_post_move = False
        if not goto_post_move:
            collide_and_slide_circle(self, obstacles, dx, dy)
        if bandit_flee:
            # if barely moved this frame, sidestep perpendicular to player to break jitter
            moved_x = self.x - oldx
            moved_y = self.y - oldy
            if abs(moved_x) < 0.25 and abs(moved_y) < 0.25:
                self._avoid_side = 1 if dxp >= 0 else -1
                self._avoid_t = max(self._avoid_t, 0.25)
            ob = getattr(self, "_hit_ob", None)
            if ob and getattr(ob, "type", "") == "Destructible":
                gp = getattr(ob, "grid_pos", None)
                if gp in game_state.obstacles:
                    del game_state.obstacles[gp]
                if getattr(ob, "health", None) is not None:
                    ob.health = 0
                cx2, cy2 = ob.rect.centerx, ob.rect.centery
                if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                    game_state.spawn_spoils(cx2, cy2, 1)
                self.gain_xp(XP_ENEMY_BLOCK)
                if random.random() < HEAL_DROP_CHANCE_BLOCK:
                    game_state.spawn_heal(cx2, cy2, HEAL_POTION_AMOUNT)
                self.bandit_break_t = max(float(getattr(self, "bandit_break_t", 0.0)), BANDIT_BREAK_SLOW_TIME)
                self._focus_block = None
        if is_bandit:
            moved_len = ((self.x - bandit_prev_pos[0]) ** 2 + (self.y - bandit_prev_pos[1]) ** 2) ** 0.5
            if moved_len < 1.0:
                self._bandit_stuck_t = float(getattr(self, "_bandit_stuck_t", 0.0)) + dt
            else:
                self._bandit_stuck_t = 0.0
            self._bandit_last_pos = (self.x, self.y)
            # Watchdog: if the bandit barely changes position over time, force a sidestep to break jitter.
            idle_pos = getattr(self, "_bandit_idle_pos", (self.x, self.y))
            idle_t = float(getattr(self, "_bandit_idle_t", 0.0)) + dt
            idle_d = ((self.x - idle_pos[0]) ** 2 + (self.y - idle_pos[1]) ** 2) ** 0.5
            if idle_d >= 30.0:
                self._bandit_idle_pos = (self.x, self.y)
                self._bandit_idle_t = 0.0
            else:
                self._bandit_idle_t = idle_t
                if idle_t >= 2.0:
                    self._avoid_side = random.choice((-1, 1))
                    self._avoid_t = max(self._avoid_t, 0.45)
                    self._ff_commit = None
                    self._ff_commit_t = 0.0
                    self._bypass_t = 0.0
                    self._bandit_idle_pos = (self.x, self.y)
                    self._bandit_idle_t = 0.0
            if bandit_flee and getattr(self, "_bandit_stuck_t", 0.0) > 0.6 and fd is not None:
                best = None
                bestd = -1
                for ny, row in enumerate(fd):
                    for nx, d in enumerate(row):
                        if (nx, ny) in game_state.obstacles:
                            continue
                        if d > bestd:
                            bestd = d
                            best = (nx, ny)
                if best:
                    self._bypass_cell = best
                    self._bypass_t = 1.2
                    self._ff_commit = None
                    self._ff_commit_t = 0.0
                    self._bandit_stuck_t = 0.0
        # Bulldozer cleanup: crush anything we hit during sweep-collision
        if getattr(self, "can_crush_all_blocks", False) and getattr(self, "_crush_queue", None):
            for ob in list(self._crush_queue):
                gp = getattr(ob, "grid_pos", None)
                if gp in game_state.obstacles:
                    del game_state.obstacles[gp]  # works for all types, incl. Indestructible & MainBlock
            self._crush_queue.clear()
            self._focus_block = None  # no longer blocked
            # Ensure 2x2 footprint is fully clear (fixes “stuck after breaking grey block”)
            try:
                r = int(getattr(self, "radius", max(8, CELL_SIZE // 3)))
                cx = self.x + self.size * 0.5
                cy = self.y + self.size * 0.5 + INFO_BAR_HEIGHT
                bb = pygame.Rect(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
                crushed_any = False
                for gp, ob in list(game_state.obstacles.items()):
                    # If the obstacle touches our collision circle’s bounding box, delete it.
                    if ob.rect.colliderect(bb):
                        del game_state.obstacles[gp]
                        crushed_any = True
                        # Only Destructible blocks drop spoils / heal, keep existing rules
                        if getattr(ob, "type", "") == "Destructible":
                            if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                                game_state.spawn_spoils(ob.rect.centerx, ob.rect.centery, 1)
                            self.gain_xp(XP_ENEMY_BLOCK)
                    if random.random() < HEAL_DROP_CHANCE_BLOCK:
                        game_state.spawn_heal(ob.rect.centerx, ob.rect.centery, HEAL_POTION_AMOUNT)
                if crushed_any:
                    self._focus_block = None
                    # prevent “stuck” heuristics from kicking in right after we bulldozed
                    if hasattr(self, "_stuck_t"):
                        self._stuck_t = 0.0
                    self.no_clip_t = max(getattr(self, 'no_clip_t', 0.0), 0.10)
            except Exception:
                pass
        # —— Bandit corner escape detection ——
        if bandit_flee:
            MIN_FRAMES_STUCK = 4
            STUCK_MOVE_THRESHOLD = CELL_SIZE * 0.30
            ESCAPE_DURATION = 0.55
            ESCAPE_TEST_STEP = CELL_SIZE * 0.6
            ob = getattr(self, "_hit_ob", None)
            collided_tile = None
            if ob and not getattr(ob, "nonblocking", False):
                gp = getattr(ob, "grid_pos", None)
                if gp is not None:
                    collided_tile = tuple(gp)
                else:
                    collided_tile = (int(ob.rect.centerx // CELL_SIZE),
                                     int((ob.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE))
            bandit_pos = (self.rect.centerx, self.rect.centery)
            if collided_tile is not None:
                if collided_tile != getattr(self, "last_collision_tile", None):
                    self.last_collision_tile = collided_tile
                    self.frames_on_same_tile = 1
                    self.stuck_origin_pos = (self.x, self.y)
                else:
                    self.frames_on_same_tile = int(getattr(self, "frames_on_same_tile", 0)) + 1
                disp = ((self.x - self.stuck_origin_pos[0]) ** 2 + (self.y - self.stuck_origin_pos[1]) ** 2) ** 0.5
                if self.frames_on_same_tile >= MIN_FRAMES_STUCK and disp <= STUCK_MOVE_THRESHOLD and getattr(self, "mode", "FLEE") != "ESCAPE_CORNER":
                    bx, by = bandit_pos
                    flee_dx, flee_dy = bx - px, by - py
                    mag = (flee_dx * flee_dx + flee_dy * flee_dy) ** 0.5 or 1.0
                    base_dir = (flee_dx / mag, flee_dy / mag)
                    left_dir = (-base_dir[1], base_dir[0])
                    right_dir = (base_dir[1], -base_dir[0])
                    # also consider directly away from obstacle center (bounce)
                    ox, oy = collided_tile
                    ob_cx = ox * CELL_SIZE + CELL_SIZE * 0.5
                    ob_cy = oy * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT
                    away_dx, away_dy = bx - ob_cx, by - ob_cy
                    away_mag = (away_dx * away_dx + away_dy * away_dy) ** 0.5 or 1.0
                    bounce_dir = (away_dx / away_mag, away_dy / away_mag)
                    candidates = [base_dir, left_dir, right_dir, bounce_dir]

                    def _dir_clear(vec):
                        tx = bx + vec[0] * ESCAPE_TEST_STEP
                        ty = by + vec[1] * ESCAPE_TEST_STEP
                        cell = (int(tx // CELL_SIZE), int((ty - INFO_BAR_HEIGHT) // CELL_SIZE))
                        if not (0 <= cell[0] < GRID_SIZE and 0 <= cell[1] < GRID_SIZE):
                            return False
                        return cell not in game_state.obstacles

                    best_dir = None
                    best_d2 = -1
                    for vec in candidates:
                        if not _dir_clear(vec):
                            continue
                        tx = bx + vec[0] * ESCAPE_TEST_STEP
                        ty = by + vec[1] * ESCAPE_TEST_STEP
                        d2p = (tx - px) ** 2 + (ty - py) ** 2
                        if d2p > best_d2:
                            best_d2 = d2p
                            best_dir = vec
                    if best_dir is None:
                        # fallback: pick any perpendicular dir that isn't blocked
                        if _dir_clear(left_dir):
                            best_dir = left_dir
                        elif _dir_clear(right_dir):
                            best_dir = right_dir
                        else:
                            best_dir = bounce_dir
                    self.escape_dir = best_dir
                    self.escape_timer = ESCAPE_DURATION
                    self.mode = "ESCAPE_CORNER"
            else:
                self.last_collision_tile = None
                self.frames_on_same_tile = 0
        # —— 卡住检测（只有“被挡住”或“无进展”才累计）——
        blocked = (self._hit_ob is not None)
        moved2 = (self.x - oldx) ** 2 + (self.y - oldy) ** 2
        min_move = 0.15 * speed_step
        min_move2 = max(0.04 * frame_scale * frame_scale, min_move * min_move)  # speed-scaled
        # 目标距离是否在本帧没有明显下降（允许轻微抖动）
        dist2 = (self.rect.centerx - int(target_cx)) ** 2 + (self.rect.centery - int(target_cy)) ** 2
        prev_d2 = getattr(self, "_prev_d2", float("inf"))
        no_progress = (dist2 > prev_d2 - 1.0)
        self._prev_d2 = dist2
        if (blocked and moved2 < min_move2) or (no_progress and moved2 < min_move2):
            self._stuck_t = getattr(self, "_stuck_t", 0.0) + dt
        else:
            self._stuck_t = 0.0
        # progress to current target (player or focus block) this frame
        dist2 = (self.rect.centerx - int(target_cx)) ** 2 + (self.rect.centery - int(target_cy)) ** 2
        prev_d2 = getattr(self, "_prev_d2", float("inf"))
        no_progress = (dist2 > prev_d2 - 1.0)  # allow tiny jitter
        self._prev_d2 = dist2
        if (blocked and moved2 < min_move2) or (no_progress and moved2 < min_move2):
            self._stuck_t = getattr(self, "_stuck_t", 0.0) + dt
        else:
            self._stuck_t = 0.0
        # 卡住 0.25s 以上：触发一次侧移（仅在“被挡住”或无进展时）
        if self._stuck_t > 0.25 and self._avoid_t <= 0.0 and (blocked or no_progress):
            self._avoid_t = random.uniform(0.25, 0.45)
            self._avoid_side = random.choice((-1, 1))
        # —— 懒 A* 兜底：长时间卡住再寻一次短路径 ——
        if self._stuck_t > 0.7 and self._avoid_t <= 0.0 and self._path_step >= len(self._path):
            # 起点：当前脚底；终点：玩家或“被锁定的可破坏物”脚底网格
            start = (gx, gy)
            if self._focus_block:
                gp = getattr(self._focus_block, "grid_pos", None)
                if gp is None:
                    cx2, cy2 = self._focus_block.rect.centerx, self._focus_block.rect.centery
                    goal = (int(cx2 // CELL_SIZE), int((cy2 - INFO_BAR_HEIGHT) // CELL_SIZE))
                else:
                    goal = gp
            else:
                goal = (int(player.rect.centerx // CELL_SIZE),
                        int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE))
            # 构图 + A*
            graph = build_graph(GRID_SIZE, game_state.obstacles)
            came, _ = a_star_search(graph, start, goal, game_state.obstacles)
            path = reconstruct_path(came, start, goal)
            # 生成“短路径”：去掉起点，只取前 6 个路点
            if len(path) > 1:
                self._path = path[1:7]
                self._path_step = 0
            # 避免立刻再次触发
            self._stuck_t = 0.0
        # 焦点块被打掉/消失 → 解除聚焦
        if self._focus_block and (self._focus_block.health is not None and self._focus_block.health <= 0):
            self._focus_block = None
        # 路径走完了就清空（下次卡住再算）
        if self._path_step >= len(self._path):
            self._path = []
            self._path_step = 0
        # 同步矩形
        self.rect.x = int(self.x)
        self.rect.y = int(self.y) + INFO_BAR_HEIGHT
        # record this frame's foot point
        self._foot_curr = (self.rect.centerx, self.rect.bottom)
        if game_state is not None and getattr(game_state, "biome_active", None) == "Scorched Hell":
            if getattr(self, "hp", 0) > 0:
                f0 = getattr(self, "_foot_prev", (self.rect.centerx, self.rect.bottom))
                f1 = getattr(self, "_foot_curr", (self.rect.centerx, self.rect.bottom))
                moved = math.hypot(f1[0] - f0[0], f1[1] - f0[1])
                if moved > 0.05:
                    hell_t = float(getattr(self, "_hell_paint_t", 0.0)) + float(dt)
                    last_pos = getattr(self, "_hell_paint_pos", None)
                    if not (isinstance(last_pos, (tuple, list)) and len(last_pos) == 2):
                        last_pos = (f1[0], f1[1])
                    dx = f1[0] - float(last_pos[0])
                    dy = f1[1] - float(last_pos[1])
                    dist = math.hypot(dx, dy)
                    if (hell_t >= HELL_ENEMY_PAINT_SPAWN_INTERVAL
                            or dist >= HELL_ENEMY_PAINT_SPAWN_DIST):
                        paint_r = enemy_paint_radius_for(self)
                        game_state.apply_enemy_paint(
                            f1[0], f1[1], paint_r,
                            paint_type="hell_trail",
                            paint_color=getattr(self, "color", None),
                        )
                        hell_t = 0.0
                        last_pos = (f1[0], f1[1])
                    self._hell_paint_t = hell_t
                    self._hell_paint_pos = last_pos
        # Let non-boss contact damage also chew through red blocks so they don't get stuck
        if not getattr(self, "is_boss", False) and self._block_contact_cd <= 0.0:
            ob_contact = getattr(self, "_hit_ob", None)
            if ob_contact and getattr(ob_contact, "type", "") == "Destructible" and getattr(ob_contact, "health",
                                                                                            None) is not None:
                mult = getattr(game_state, "biome_enemy_contact_mult", 1.0)
                block_dmg = int(round(ENEMY_CONTACT_DAMAGE * max(1.0, mult)))
                ob_contact.health -= block_dmg
                self._block_contact_cd = float(PLAYER_HIT_COOLDOWN)
                if ob_contact.health <= 0:
                    gp = getattr(ob_contact, "grid_pos", None)
                    if gp in game_state.obstacles:
                        del game_state.obstacles[gp]
                    cx2, cy2 = ob_contact.rect.centerx, ob_contact.rect.centery
                    if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                        game_state.spawn_spoils(cx2, cy2, 1)
                    self.gain_xp(XP_ENEMY_BLOCK)
                    if random.random() < HEAL_DROP_CHANCE_BLOCK:
                        game_state.spawn_heal(cx2, cy2, HEAL_POTION_AMOUNT)
                    self._focus_block = None
        # 圆心是否触到障碍 → Boss可直接碾碎，否则按原CD打可破坏物
        if self.attack_timer >= attack_interval:
            cx = self.x + self.size * 0.5
            cy = self.y + self.size * 0.5 + INFO_BAR_HEIGHT
            for ob in list(obstacles):
                if ob.rect.inflate(self.radius * 2, self.radius * 2).collidepoint(cx, cy):
                    if getattr(self, "can_crush_all_blocks", False):
                        # Bulldozer path: remove ANY obstacle it touches
                        gp = getattr(ob, "grid_pos", None)
                        if gp in game_state.obstacles:
                            del game_state.obstacles[gp]
                        # keep drops only for destructible; indestructible gives nothing
                        if getattr(ob, "type", "") == "Destructible":
                            cx2, cy2 = ob.rect.centerx, ob.rect.centery
                            if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                                game_state.spawn_spoils(cx2, cy2, 1)
                            self.gain_xp(XP_ENEMY_BLOCK)
                            if random.random() < HEAL_DROP_CHANCE_BLOCK:
                                game_state.spawn_heal(cx2, cy2, HEAL_POTION_AMOUNT)
                        self.attack_timer = 0.0
                        self._focus_block = None
                    else:
                        # Non-boss: original behavior vs. Destructible
                        if getattr(ob, "type", "") == "Destructible":
                            ob.health -= self.attack
                            self.attack_timer = 0.0
                            if ob.health <= 0:
                                gp = ob.grid_pos
                                if gp in game_state.obstacles: del game_state.obstacles[gp]
                                cx2, cy2 = ob.rect.centerx, ob.rect.centery
                                if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                                    game_state.spawn_spoils(cx2, cy2, 1)
                                self.gain_xp(XP_ENEMY_BLOCK)
                                if random.random() < HEAL_DROP_CHANCE_BLOCK:
                                    game_state.spawn_heal(cx2, cy2, HEAL_POTION_AMOUNT)
                    break

    def update_special(self, dt: float, player: 'Player', enemies: List['Enemy'],
                       enemy_shots: List['EnemyShot'], game_state: 'GameState' = None):
        # --- frame-local centers (avoid UnboundLocal on cx/cy/px/py) ---
        cx, cy = self.rect.centerx, self.rect.centery
        px, py = player.rect.centerx, player.rect.centery
        # --- Splinter passive split when HP <= 50% (non-lethal path) ---
        if self._can_split and not self._split_done and self.hp > 0 and self.hp <= int(self.max_hp * 0.5):
            # 标记已分裂，生成子体并移除自己
            self._split_done = True
            self._can_split = False
            spawn_splinter_children(
                self, enemies, game_state,
                level_idx=getattr(game_state, "current_level", 0),
                wave_index=0
            )
            # 将自己“杀死”以便主循环移除（或者直接把 hp 置 0）
            self.hp = 0
            return
        if self.type == "ravager":
            cd_min, cd_max = RAVAGER_DASH_CD_RANGE
            if not hasattr(self, "_dash_state"):
                self._dash_state = "idle"
                self._dash_cd = random.uniform(cd_min, cd_max)
                self._dash_t = 0.0
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0
            if getattr(self, "_dash_state", "") != "go" and getattr(self, "can_crush_all_blocks", False):
                self.can_crush_all_blocks = False
            self._dash_cd = max(0.0, (self._dash_cd or 0.0) - dt)
            if self._dash_state == "idle" and self._dash_cd <= 0.0:
                vx, vy = px - cx, py - cy
                L = (vx * vx + vy * vy) ** 0.5 or 1.0
                self._dash_dir = (vx / L, vy / L)
                self._dash_state = "wind"
                self._dash_t = RAVAGER_DASH_WINDUP
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0
                self.speed = max(0.2, self._dash_speed_hold * 0.35)
                if game_state:
                    game_state.spawn_telegraph(cx, cy, r=int(getattr(self, "radius", self.size * 0.5) * 0.9),
                                               life=self._dash_t, kind="ravager_dash", payload=None)
            elif self._dash_state == "wind":
                self._dash_t -= dt
                self.speed = max(0.2, self._dash_speed_hold * 0.35)
                if self._dash_t <= 0.0:
                    self._dash_state = "go"
                    self._dash_t = RAVAGER_DASH_TIME
                    self.speed = self._dash_speed_hold
                    self.buff_spd_add = float(getattr(self, "buff_spd_add", 0.0)) + float(self._dash_speed_hold) * (
                                RAVAGER_DASH_SPEED_MULT - 1.0)
                    self.buff_t = max(getattr(self, "buff_t", 0.0), self._dash_t)
                    self.no_clip_t = max(getattr(self, "no_clip_t", 0.0), self._dash_t + 0.05)
                    self.can_crush_all_blocks = True
                    self._dash_cd = random.uniform(cd_min, cd_max)
            elif self._dash_state == "go":
                self._dash_t -= dt
                self.can_crush_all_blocks = True
                self.no_clip_t = max(getattr(self, "no_clip_t", 0.0), 0.05)
                self._ghost_accum += dt
                f0 = getattr(self, "_foot_prev", (self.rect.centerx, self.rect.bottom))
                f1 = getattr(self, "_foot_curr", (self.rect.centerx, self.rect.bottom))
                n = int(self._ghost_accum // AFTERIMAGE_INTERVAL)
                if n > 0:
                    self._ghost_accum -= n * AFTERIMAGE_INTERVAL
                    for i in range(n):
                        t = (i + 1) / (n + 1)
                        gx = f0[0] * (1 - t) + f1[0] * t
                        gy = f0[1] * (1 - t) + f1[1] * t
                        ghost_size = int(self.size * 2)
                        ghost_sprite = _enemy_sprite("ravager", ghost_size)
                        game_state.ghosts.append(
                            AfterImageGhost(
                                gx, gy, ghost_size, ghost_size,
                                ENEMY_COLORS.get("ravager", self.color),
                                ttl=AFTERIMAGE_TTL,
                                sprite=ghost_sprite,
                            )
                        )
                if self._dash_t <= 0.0:
                    self._dash_state = "idle"
                    self.can_crush_all_blocks = False
            else:
                self.can_crush_all_blocks = False
        if getattr(self, "is_boss", False) and getattr(self, "hp", 0) <= 0:
            trigger_twin_enrage(self, enemies, game_state)
        # 远程怪：发射投射物
        if self.type in ("ranged", "spitter"):
            self.ranged_cd = max(0.0, (self.ranged_cd or 0.0) - dt)
            if self.ranged_cd <= 0.0:
                # 朝玩家中心发射
                cx, cy = self.rect.centerx, self.rect.centery
                px, py = player.rect.centerx, player.rect.centery
                dx, dy = px - cx, py - cy
                L = (dx * dx + dy * dy) ** 0.5 or 1.0
                vx, vy = dx / L * RANGED_PROJ_SPEED, dy / L * RANGED_PROJ_SPEED
                enemy_shots.append(EnemyShot(cx, cy, vx, vy, RANGED_PROJ_DAMAGE))
                self.ranged_cd = RANGED_COOLDOWN
        # 自爆怪：接近玩家后才启动引信；到时爆炸
        if self.type in ("suicide", "bomber"):
            cx, cy = self.rect.centerx, self.rect.centery
            pr = player.rect
            dx, dy = pr.centerx - cx, pr.centery - cy
            dist = (dx * dx + dy * dy) ** 0.5
            # Arm when close enough
            if (not getattr(self, "suicide_armed", False)) and dist <= SUICIDE_ARM_DIST:
                self.suicide_armed = True
                self.fuse = float(SUICIDE_FUSE)
            # Ticking fuse
            if getattr(self, "suicide_armed", False) and (self.fuse is not None):
                self.fuse -= dt
                if self.fuse <= 0.0:
                    # explode
                    if dist <= SUICIDE_RADIUS and player.hit_cd <= 0.0:
                        game_state.damage_player(player, SUICIDE_DAMAGE)
                        player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                    self.hp = 0  # remove self
        if self.type == "ravager":
            cd_min, cd_max = RAVAGER_DASH_CD_RANGE
            if not hasattr(self, "_dash_state"):
                self._dash_state = "idle"
                self._dash_cd = random.uniform(cd_min, cd_max)
                self._dash_t = 0.0
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0
            if getattr(self, "_dash_state", "") != "go" and getattr(self, "can_crush_all_blocks", False):
                self.can_crush_all_blocks = False
            self._dash_cd = max(0.0, (self._dash_cd or 0.0) - dt)
            if self._dash_state == "idle" and self._dash_cd <= 0.0:
                vx, vy = px - cx, py - cy
                L = (vx * vx + vy * vy) ** 0.5 or 1.0
                self._dash_dir = (vx / L, vy / L)
                self._dash_state = "wind"
                self._dash_t = RAVAGER_DASH_WINDUP
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0
                self.speed = max(0.2, self._dash_speed_hold * 0.35)
                if game_state:
                    game_state.spawn_telegraph(cx, cy, r=int(getattr(self, "radius", self.size * 0.5) * 0.9),
                                               life=self._dash_t, kind="ravager_dash", payload=None)
            elif self._dash_state == "wind":
                self._dash_t -= dt
                self.speed = max(0.2, self._dash_speed_hold * 0.35)
                if self._dash_t <= 0.0:
                    self._dash_state = "go"
                    self._dash_t = RAVAGER_DASH_TIME
                    self.speed = self._dash_speed_hold
                    self.buff_spd_add = float(getattr(self, "buff_spd_add", 0.0)) + float(self._dash_speed_hold) * (
                                RAVAGER_DASH_SPEED_MULT - 1.0)
                    self.buff_t = max(getattr(self, "buff_t", 0.0), self._dash_t)
                    self.no_clip_t = max(getattr(self, "no_clip_t", 0.0), self._dash_t + 0.05)
                    self.can_crush_all_blocks = True
                    self._dash_cd = random.uniform(cd_min, cd_max)
            elif self._dash_state == "go":
                self._dash_t -= dt
                self.can_crush_all_blocks = True
                self.no_clip_t = max(getattr(self, "no_clip_t", 0.0), 0.05)
                self._ghost_accum += dt
                f0 = getattr(self, "_foot_prev", (self.rect.centerx, self.rect.bottom))
                f1 = getattr(self, "_foot_curr", (self.rect.centerx, self.rect.bottom))
                n = int(self._ghost_accum // AFTERIMAGE_INTERVAL)
                if n > 0:
                    self._ghost_accum -= n * AFTERIMAGE_INTERVAL
                    for i in range(n):
                        t = (i + 1) / (n + 1)
                        gx = f0[0] * (1 - t) + f1[0] * t
                        gy = f0[1] * (1 - t) + f1[1] * t
                        game_state.ghosts.append(
                            AfterImageGhost(gx, gy, self.size, self.size, ENEMY_COLORS.get("ravager", self.color),
                                            ttl=AFTERIMAGE_TTL))
                if self._dash_t <= 0.0:
                    self._dash_state = "idle"
                    self.can_crush_all_blocks = False
            else:
                self.can_crush_all_blocks = False
        if getattr(self, "is_boss", False) and getattr(self, "hp", 0) <= 0:
            trigger_twin_enrage(self, enemies, game_state)
        # 增益怪：周期性为周围友军加 BUFF
        if self.type == "buffer":
            self.buff_cd = max(0.0, (self.buff_cd or 0.0) - dt)
            if self.buff_cd <= 0.0:
                cx, cy = self.rect.centerx, self.rect.centery
                for z in enemies:
                    zx, zy = z.rect.centerx, z.rect.centery
                    if (zx - cx) ** 2 + (zy - cy) ** 2 <= BUFF_RADIUS ** 2:
                        z.buff_t = BUFF_DURATION
                        z.buff_atk_mult = BUFF_ATK_MULT
                        z.buff_spd_add = BUFF_SPD_ADD
                self.buff_cd = BUFF_COOLDOWN
        # 护盾怪：周期性给周围友军加护盾
        if self.type == "shielder":
            self.shield_cd = max(0.0, (self.shield_cd or 0.0) - dt)
            # 同时衰减自身护盾
            if self.shield_hp > 0:
                self.shield_t -= dt
                if self.shield_t <= 0:
                    self.shield_hp = 0
                if self.shield_cd <= 0.0:
                    cx, cy = self.rect.centerx, self.rect.centery
                    for z in enemies:
                        zx, zy = z.rect.centerx, z.rect.centery
                        if (zx - cx) ** 2 + (zy - cy) ** 2 <= SHIELD_RADIUS ** 2:
                            z.shield_hp = SHIELD_AMOUNT
                            z.shield_t = SHIELD_DURATION
                    self.shield_cd = SHIELD_COOLDOWN
        # ==== 金币大盗：持续偷钱、计时逃脱 ====
        if getattr(self, "type", "") == "bandit":
            bandit_wind_trapped = bool(getattr(self, "_wind_trapped", False))
            # 光环动画相位（1.2s 一次完整扩散）
            self._aura_t = (getattr(self, "_aura_t", 0.0) + dt / 1.2) % 1.0
            # 持续闪金光（维持金色淡晕）
            self._gold_glow_t = max(self._gold_glow_t, 0.2)
            if getattr(self, "radar_slow_left", 0.0) > 0.0:
                self.radar_slow_left = max(0.0, float(getattr(self, "radar_slow_left", 0.0)) - dt)
                if self.radar_slow_left <= 0.0 and hasattr(self, "_radar_base_speed"):
                    self.speed = float(getattr(self, "_radar_base_speed", self.speed))
            if getattr(self, "radar_tagged", False):
                self.radar_ring_phase = (float(getattr(self, "radar_ring_phase", 0.0)) + dt) % float(getattr(self, "radar_ring_period", 2.0))
            # 偷钱累积：以秒为单位的离散扣除，避免浮点抖动
            self._steal_accum += float(getattr(self, "steal_per_sec", BANDIT_STEAL_RATE_MIN)) * dt
            steal_units = int(self._steal_accum)
            if steal_units >= 1 and game_state is not None:
                self._steal_accum -= steal_units
                # steal from total (level spoils + bank), prefer draining level spoils first
                lvl = int(getattr(game_state, "spoils_gained", 0))
                bank = int(META.get("spoils", 0))
                total_avail = max(0, lvl + bank)
                lb_lvl = int(getattr(self, "lockbox_level", META.get("lockbox_level", 0)))
                lock_floor = 0
                if lb_lvl > 0:
                    lock_floor = int(getattr(self, "lockbox_floor", 0))
                    if lock_floor <= 0:
                        baseline = int(getattr(self, "lockbox_baseline", total_avail))
                        lock_floor = lockbox_protected_min(baseline, lb_lvl)
                        self.lockbox_level = lb_lvl
                        self.lockbox_baseline = baseline
                        self.lockbox_floor = lock_floor
                    lock_floor = min(lock_floor, total_avail)
                stealable_cap = max(0, total_avail - lock_floor)
                got = min(steal_units, stealable_cap)
                if got > 0:
                    take_lvl = min(lvl, got)
                    if take_lvl:
                        game_state.spoils_gained = lvl - take_lvl
                    rest = got - take_lvl
                    if rest:
                        META["spoils"] = max(0, bank - rest)
                    self._stolen_total = int(getattr(self, "_stolen_total", 0)) + got
                    game_state._bandit_stolen = int(getattr(game_state, "_bandit_stolen", 0)) + got
                    # 飘字提示（-金币）
                    cx, cy = self.rect.centerx, self.rect.centery
                    game_state.add_damage_text(cx, cy - 18, f"-{got}", crit=True, kind="hp")
            # 逃跑计时
            current_escape = float(getattr(self, "escape_t", BANDIT_ESCAPE_TIME_BASE))
            if bandit_wind_trapped:
                # Freeze the escape timer while trapped in wind to prevent fleeing
                self.escape_t = max(0.0, current_escape)
            else:
                self.escape_t = max(0.0, current_escape - dt)
            if self.escape_t <= 0.0 and not bandit_wind_trapped:
                if game_state is not None:
                    # 小飘字（保留）
                    game_state.add_damage_text(self.rect.centerx, self.rect.centery, "ESCAPED", crit=False,
                                               kind="shield")
                    stolen = int(getattr(self, "_stolen_total", 0))
                    game_state.flash_banner(f"BANDIT ESCAPED — STOLEN {stolen} COINS", sec=1.0)
                try:
                    enemies.remove(self)
                except Exception:
                    pass
                return
        # 小雾妖：可被攻击；死时自爆；计时≥10s 会被 Boss 收回（由 Boss 侧结算回血）
        if self.type == "mistling":
            # 计时
            self._life = getattr(self, "_life", 0.0) + dt
            # 被击杀 → 自爆（一次性）
            if self.hp <= 0 and not getattr(self, "_boom_done", False):
                cx, cy = self.rect.centerx, self.rect.centery
                pr = player.rect
                if (pr.centerx - cx) ** 2 + (pr.centery - cy) ** 2 <= (MISTLING_BLAST_RADIUS ** 2):
                    if player.hit_cd <= 0.0:
                        game_state.damage_player(player, MISTLING_BLAST_DAMAGE)
                        player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                self._boom_done = True
                # 允许主循环正常移除
        # 腐蚀幼体：死亡留酸；计时>15s 可被BOSS吸回
        if self.type == "corruptling":
            self._life = getattr(self, "_life", 0.0) + dt
            if self.hp <= 0 and not getattr(self, "_acid_on_death", False):
                game_state.spawn_acid_pool(self.rect.centerx, self.rect.centery, r=20, life=4.0, dps=ACID_DPS * 0.8)
                self._acid_on_death = True  # 让后续移除流程照常进行
            # 吸附由 BOSS 侧发起，这里只负责寿命记录
        # 记忆吞噬者（boss_mem）
        if getattr(self, "is_boss", False) and getattr(self, "type", "") == "boss_mem":
            enraged = bool(getattr(self, "is_enraged", False))
            hp_pct = max(0.0, self.hp / max(1, self.max_hp))
            hp_pct_effective = 0.0 if enraged else hp_pct  # enraged: ignore HP gates for skills
            cd_mult = float(getattr(self, "_enrage_cd_mult", 1.0))
            # 阶段切换
            if enraged:
                self.phase = 3
            else:
                if hp_pct > 0.70:
                    self.phase = 1
                elif hp_pct > 0.40:
                    self.phase = 2
                else:
                    self.phase = 3
            # 基础冷却
            self._spit_cd = max(0.0, getattr(self, "_spit_cd", 0.0) - dt)
            self._split_cd = max(0.0, getattr(self, "_split_cd", 0.0) - dt)

            # Higher stages retain lower-stage skills (2 keeps 1; 3 keeps 1+2)
            phase1_ok = enraged or self.phase >= 1
            phase2_ok = enraged or self.phase >= 2
            phase3_ok = enraged or self.phase >= 3
            # 阶段1：腐蚀喷吐 + 小怪 2 个/20s
            if phase1_ok:
                if self._spit_cd <= 0.0:
                    # 以玩家方向的扇形在地面“预警→落酸”
                    px, py = player.rect.centerx, player.rect.centery
                    ang = math.atan2(py - cy, px - cx)
                    points = []
                    for w in range(SPIT_WAVES_P1):
                        for i in range(SPIT_PUDDLES_PER_WAVE):
                            off_ang = ang + math.radians(random.uniform(-SPIT_CONE_DEG / 2, SPIT_CONE_DEG / 2))
                            dist = (SPIT_RANGE * (i + 1) / SPIT_PUDDLES_PER_WAVE) * random.uniform(0.6, 1.0)
                            points.append((cx + math.cos(off_ang) * dist, cy + math.sin(off_ang) * dist))
                    game_state.spawn_telegraph(cx, cy, r=28, life=ACID_TELEGRAPH_T, kind="acid",
                                               payload={"points": points, "radius": 24, "life": ACID_LIFETIME,
                                                        "dps": ACID_DPS, "slow": ACID_SLOW_FRAC})
                    self._spit_cd = 5.0 * cd_mult
                if self._split_cd <= 0.0:
                    for _ in range(2):
                        enemies.append(spawn_corruptling_at(cx + random.randint(-20, 20), cy + random.randint(-20, 20)))
                    self._split_cd = SPLIT_CD_P1 * cd_mult
            # 阶段2：移动略快；喷吐“连续两次”；召唤 3 个/15s；吸附融合
            if phase2_ok:
                self.speed = max(MEMDEV_SPEED, MEMDEV_SPEED + 0.5)
                if self._spit_cd <= 0.0:
                    for _ in range(2):  # 连续两次
                        px, py = player.rect.centerx, player.rect.centery
                        ang = math.atan2(py - cy, px - cx)
                        points = []
                        for w in range(SPIT_WAVES_P1):
                            for i in range(SPIT_PUDDLES_PER_WAVE):
                                off_ang = ang + math.radians(random.uniform(-SPIT_CONE_DEG / 2, SPIT_CONE_DEG / 2))
                                dist = (SPIT_RANGE * (i + 1) / SPIT_PUDDLES_PER_WAVE) * random.uniform(0.6, 1.0)
                                points.append((cx + math.cos(off_ang) * dist, cy + math.sin(off_ang) * dist))
                        game_state.spawn_telegraph(cx, cy, r=32, life=ACID_TELEGRAPH_T, kind="acid",
                                                   payload={"points": points, "radius": 26, "life": ACID_LIFETIME,
                                                            "dps": ACID_DPS, "slow": ACID_SLOW_FRAC})
                    self._spit_cd = 4.0 * cd_mult
                if self._split_cd <= 0.0:
                    for _ in range(3):
                        enemies.append(spawn_corruptling_at(cx + random.randint(-20, 20), cy + random.randint(-20, 20)))
                    self._split_cd = SPLIT_CD_P2 * cd_mult
                # 吸附融合：场上活过 15s 的腐蚀幼体被拉回并回血
                pull_any = False
                for z in list(enemies):
                    if getattr(z, "type", "") == "corruptling" and getattr(z, "_life", 0.0) >= FUSION_LIFETIME:
                        zx, zy = z.rect.centerx, z.rect.centery
                        if (zx - cx) ** 2 + (zy - cy) ** 2 <= FUSION_PULL_RADIUS ** 2:
                            z.hp = 0  # kill
                            self.hp = min(self.max_hp, self.hp + FUSION_HEAL)
                            pull_any = True
                if pull_any:
                    # 可选：加一个小数字飘字：+HP
                    game_state.add_damage_text(cx, cy, +FUSION_HEAL, crit=False, kind="shield")  # 蓝色表示护盾/回复
            # 阶段3：全屏酸爆(每降 10%一次) + 继续召唤；<10% 濒死冲锋
            if phase3_ok:
                # 全屏酸爆：按阈值触发
                next_pct = getattr(self, "_rain_next_pct", 0.40)
                while hp_pct_effective <= next_pct and next_pct >= 0.0:
                    # 随机铺点（带预警）
                    pts = []
                    for _ in range(RAIN_PUDDLES):
                        gx = random.randint(0, GRID_SIZE - 1)
                        gy = random.randint(0, GRID_SIZE - 1)
                        pts.append((gx * CELL_SIZE + CELL_SIZE // 2, gy * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT))
                    game_state.spawn_telegraph(cx, cy, r=36, life=RAIN_TELEGRAPH_T, kind="acid",
                                               payload={"points": pts, "radius": 22, "life": ACID_LIFETIME,
                                                        "dps": ACID_DPS, "slow": ACID_SLOW_FRAC})
                    next_pct -= RAIN_STEP
                    self._rain_next_pct = next_pct
                # 继续召唤（比P2略低频防爆场）
                if self._split_cd <= 0.0:
                    for _ in range(2):
                        enemies.append(spawn_corruptling_at(cx + random.randint(-20, 20), cy + random.randint(-20, 20)))
                    self._split_cd = 12.0 * cd_mult
                # 濒死冲锋
                if hp_pct_effective <= CHARGE_THRESH and not getattr(self, "_charging", False):
                    self._charging = True
                    # 直接朝玩家方向加速移动，不受可破坏物阻挡（移动层会处理破坏）
                    self.speed = CHARGE_SPEED
            # ===== Boss：蓄力冲刺（全阶段可触发） =====
            if not hasattr(self, "_dash_state"):
                self._dash_state = "idle"
                self._dash_cd = random.uniform(4.5, 6.0) * cd_mult
                # initial dash cooldown already scaled by cd_mult
                self._dash_t = 0.0
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0  # 残影生成计时器
            # 冷却推进
            self._dash_cd = max(0.0, self._dash_cd - dt)
            # 进入“蓄力”
            if self._dash_state == "idle" and self._dash_cd <= 0.0 and not getattr(self, "_charging", False):
                px, py = player.rect.centerx, player.rect.centery
                cx, cy = self.rect.centerx, self.rect.centery
                vx, vy = px - cx, py - cy
                L = (vx * vx + vy * vy) ** 0.5 or 1.0
                self._dash_dir = (vx / L, vy / L)
                self._dash_state = "wind"
                self._dash_t = BOSS_DASH_WINDUP
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0
                # 蓄力时显著减速
                self.speed = max(0.2, self._dash_speed_hold * 0.25)
                # 视觉预警：中心圈（可保留；不想要可以注释）
                game_state.spawn_telegraph(cx, cy, r=int(getattr(self, "radius", self.size * 0.5) * 0.9),
                                           life=self._dash_t, kind="acid", payload=None)
            elif self._dash_state == "wind":
                self._dash_t -= dt
                self.speed = max(0.2, self._dash_speed_hold * 0.25)
                if self._dash_t <= 0.0:
                    self._dash_state = "go"
                    self._dash_t = BOSS_DASH_GO_TIME
                    self.speed = self._dash_speed_hold  # 恢复基础，实际提速走 buff
                    dash_mult = BOSS_DASH_SPEED_MULT_ENRAGED if getattr(self, "is_enraged",
                                                                        False) else BOSS_DASH_SPEED_MULT
                    self.buff_spd_add = float(getattr(self, "buff_spd_add", 0.0)) + float(self._dash_speed_hold) * (
                            dash_mult - 1.0)
                    self.buff_t = max(getattr(self, "buff_t", 0.0), self._dash_t)
                    # 短暂无视碰撞：冲刺更“果断”
                    self.no_clip_t = max(getattr(self, "no_clip_t", 0.0), self._dash_t + 0.05)
                    # 预设下次冷却，稍后在 go 结束时生效（避免 wind 期间被改动）
                    self._dash_cd_next = random.uniform(4.5, 6.0)
            elif self._dash_state == "go":
                self._dash_t -= dt
                # emit ghosts along the actual path covered this frame (trailing)
                self._ghost_accum += dt
                f0 = getattr(self, "_foot_prev", (self.rect.centerx, self.rect.bottom))  # last frame foot
                f1 = getattr(self, "_foot_curr", (self.rect.centerx, self.rect.bottom))  # this frame foot
                n = int(self._ghost_accum // AFTERIMAGE_INTERVAL)
                if n > 0:
                    self._ghost_accum -= n * AFTERIMAGE_INTERVAL
                    # place n ghosts between f0→f1 (closer to f0 = looks behind)
                    for i in range(n):
                        t = (i + 1) / (n + 1)  # 0 < t < 1
                        gx = f0[0] * (1 - t) + f1[0] * t
                        gy = f0[1] * (1 - t) + f1[1] * t
                        game_state.ghosts.append(
                            AfterImageGhost(gx, gy, self.size, self.size, self.color, ttl=AFTERIMAGE_TTL))
                if self._dash_t <= 0.0:
                    self._dash_state = "idle"
                    next_cd = getattr(self, "_dash_cd_next", None)
                    if next_cd is None:
                        next_cd = random.uniform(4.5, 6.0)
                    self._dash_cd = next_cd * cd_mult
                    self._dash_cd_next = None
    def draw(self, screen):
        if getattr(self, "type", "") == "bandit":
            cx, cy = self.rect.centerx, self.rect.bottom
            t = float(getattr(self, "_aura_t", 0.0)) % 1.0
            base_r = max(16, int(self.radius * 7.0))
            r = int(base_r + (self.radius * 1.2) * t)
            alpha = int(210 - 150 * t)
            s = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
            pygame.draw.circle(s, (255, 215, 0, int(alpha * 0.35)), (r + 3, r + 3), r)
            pygame.draw.circle(s, (255, 215, 0, alpha), (r + 3, r + 3), r, width=5)
            screen.blit(s, (cx - r - 3, cy - r - 3))
            if getattr(self, "radar_tagged", False):
                rr = max(20, int(self.radius * 3.0))
                ring = pygame.Surface((rr * 2 + 10, rr * 2 + 10), pygame.SRCALPHA)
                pygame.draw.circle(ring, (255, 60, 60, 220), (rr + 5, rr + 5), rr, width=6)
                screen.blit(ring, (self.rect.centerx - rr - 5, self.rect.centery - rr - 5))
        fallback = ENEMY_COLORS.get(getattr(self, "type", "basic"), (255, 60, 60))
        color = getattr(self, "_current_color", fallback)
        pygame.draw.rect(screen, color, self.rect)
        if getattr(self, "is_enraged", False):
            pad = 6
            glow_rect = self.rect.inflate(pad * 2, pad * 2)
            glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
            pulse = 150 + int(60 * math.sin(pygame.time.get_ticks() * 0.02))
            pygame.draw.rect(glow,
                             (min(255, max(0, color[0])),
                              min(255, max(0, color[1])),
                              min(255, max(0, color[2])),
                              min(255, max(80, pulse))),
                             glow.get_rect(),
                             width=3,
                             border_radius=8)
            screen.blit(glow, glow_rect.topleft)
'''


def install(game):
    local_ns = {}
    exec(ENEMY_CORE_SOURCE, game.__dict__, local_ns)
    game.__dict__.update({name: local_ns[name] for name in ("AfterImageGhost", "Enemy")})
    return local_ns["AfterImageGhost"], local_ns["Enemy"]
