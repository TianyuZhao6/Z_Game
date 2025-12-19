#include <SDL.h>
#include <SDL_ttf.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <limits>
#include <optional>
#include <queue>
#include <random>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

// Basic config mirrored from ZGame.py (values trimmed for a single-file port)
constexpr const char* GAME_TITLE = "NEURONVIVOR";
constexpr int INFO_BAR_HEIGHT = 40;
constexpr int GRID_SIZE = 36;
constexpr int CELL_SIZE = 40;
constexpr int WINDOW_SIZE = GRID_SIZE * CELL_SIZE;
constexpr int TOTAL_HEIGHT = WINDOW_SIZE + INFO_BAR_HEIGHT;
constexpr int OBSTACLE_HEALTH = 20;
constexpr int MAIN_BLOCK_HEALTH = 40;
constexpr float DESTRUCTIBLE_RATIO = 0.3f;
constexpr int PLAYER_SPEED = 5;
constexpr int ENEMY_SPEED = 2;
constexpr int ENEMY_ATTACK = 10;

using GridPos = std::pair<int, int>;

struct PairHash {
    std::size_t operator()(const GridPos& p) const noexcept {
        return (static_cast<std::size_t>(p.first) << 32) ^ static_cast<std::size_t>(p.second);
    }
};

static std::mt19937 rng{std::random_device{}()};

int rand_int(int min, int max) {
    std::uniform_int_distribution<int> dist(min, max);
    return dist(rng);
}

float rand_float(float min, float max) {
    std::uniform_real_distribution<float> dist(min, max);
    return dist(rng);
}

// Font cache
TTF_Font* load_font(int size) {
    static std::unordered_map<int, TTF_Font*> cache;
    auto it = cache.find(size);
    if (it != cache.end()) return it->second;
    const std::array<std::string, 6> candidates = {
        "assets/fonts/Sekuya-Regular.ttf",
        "assets/fonts/Sekuya.ttf",
        "assets/fonts/arial.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf"
    };
    TTF_Font* font = nullptr;
    for (const auto& path : candidates) {
        if (!std::filesystem::exists(path)) continue;
        font = TTF_OpenFont(path.c_str(), size);
        if (font) break;
    }
    if (!font) return nullptr;
    cache[size] = font;
    return font;
}

SDL_Texture* render_text(SDL_Renderer* renderer, const std::string& text, int size, SDL_Color color) {
    TTF_Font* font = load_font(size);
    if (!font) return nullptr;
    SDL_Surface* surf = TTF_RenderUTF8_Blended(font, text.c_str(), color);
    if (!surf) return nullptr;
    SDL_Texture* tex = SDL_CreateTextureFromSurface(renderer, surf);
    SDL_FreeSurface(surf);
    return tex;
}

void draw_text(SDL_Renderer* renderer, const std::string& text, int size, SDL_Color color, int x, int y) {
    SDL_Texture* tex = render_text(renderer, text, size, color);
    if (!tex) return;
    int w, h;
    SDL_QueryTexture(tex, nullptr, nullptr, &w, &h);
    SDL_Rect dst{x, y, w, h};
    SDL_RenderCopy(renderer, tex, nullptr, &dst);
    SDL_DestroyTexture(tex);
}

SDL_Rect draw_button(SDL_Renderer* renderer, const std::string& label, int x, int y,
                     int w = 180, int h = 56,
                     SDL_Color bg = {40, 40, 40, 255},
                     SDL_Color fg = {240, 240, 240, 255},
                     SDL_Color border = {15, 15, 15, 255}) {
    SDL_Rect rect{x, y, w, h};
    SDL_Rect border_rect{x - 3, y - 3, w + 6, h + 6};
    SDL_SetRenderDrawColor(renderer, border.r, border.g, border.b, 255);
    SDL_RenderFillRect(renderer, &border_rect);
    SDL_SetRenderDrawColor(renderer, bg.r, bg.g, bg.b, 255);
    SDL_RenderFillRect(renderer, &rect);
    SDL_Texture* text = render_text(renderer, label, 28, fg);
    if (text) {
        int tw, th;
        SDL_QueryTexture(text, nullptr, nullptr, &tw, &th);
        SDL_Rect dst{x + (w - tw) / 2, y + (h - th) / 2, tw, th};
        SDL_RenderCopy(renderer, text, nullptr, &dst);
        SDL_DestroyTexture(text);
    }
    return rect;
}

bool point_in_rect(const SDL_Rect& rect, int px, int py) {
    return px >= rect.x && px <= rect.x + rect.w && py >= rect.y && py <= rect.y + rect.h;
}

void door_transition(SDL_Renderer* renderer, SDL_Color color = {0, 0, 0, 255}, int duration_ms = 500) {
    const int door_width = WINDOW_SIZE / 2;
    SDL_Rect left{0, 0, 0, TOTAL_HEIGHT};
    SDL_Rect right{WINDOW_SIZE, 0, 0, TOTAL_HEIGHT};
    Uint32 start = SDL_GetTicks();
    while (true) {
        Uint32 elapsed = SDL_GetTicks() - start;
        float progress = std::min(1.0f, elapsed / static_cast<float>(duration_ms));
        int lw = static_cast<int>(door_width * progress);
        int rw = static_cast<int>(door_width * progress);
        left.w = lw;
        right.x = WINDOW_SIZE - rw;
        right.w = rw;
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
        SDL_RenderClear(renderer);
        SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, 255);
        SDL_RenderFillRect(renderer, &left);
        SDL_RenderFillRect(renderer, &right);
        SDL_RenderPresent(renderer);
        if (progress >= 1.0f) break;
        SDL_Delay(16);
    }
}
struct Graph {
    std::unordered_map<GridPos, std::vector<GridPos>, PairHash> edges;
    std::unordered_map<long long, float> weights;

    static long long edge_key(const GridPos& a, const GridPos& b) {
        return (static_cast<long long>(a.first) & 0xFFFF) << 48 |
               (static_cast<long long>(a.second) & 0xFFFF) << 32 |
               (static_cast<long long>(b.first) & 0xFFFF) << 16 |
               (static_cast<long long>(b.second) & 0xFFFF);
    }

    void add_edge(const GridPos& a, const GridPos& b, float w) {
        edges[a].push_back(b);
        weights[edge_key(a, b)] = w;
    }

    const std::vector<GridPos>& neighbors(const GridPos& node) const {
        static const std::vector<GridPos> empty;
        auto it = edges.find(node);
        return it == edges.end() ? empty : it->second;
    }

    float cost(const GridPos& a, const GridPos& b) const {
        auto it = weights.find(edge_key(a, b));
        return it == weights.end() ? std::numeric_limits<float>::infinity() : it->second;
    }
};

struct Obstacle {
    SDL_Rect rect{};
    std::string type;
    int health{};
    bool is_main_block{false};
    bool nonblocking{false};

    Obstacle() = default;
    Obstacle(int gx, int gy, const std::string& t, int hp = 0) : type(t), health(hp) {
        rect = SDL_Rect{gx * CELL_SIZE, gy * CELL_SIZE + INFO_BAR_HEIGHT, CELL_SIZE, CELL_SIZE};
    }

    bool is_destroyed() const {
        return type == "Destructible" && health <= 0;
    }

    GridPos grid_pos() const {
        return {rect.x / CELL_SIZE, (rect.y - INFO_BAR_HEIGHT) / CELL_SIZE};
    }
};

struct Item {
    int x{};
    int y{};
    bool is_main{false};
    int radius{};
    SDL_Point center{};
    SDL_Rect rect{};

    Item(int gx, int gy, bool main_item = false) : x(gx), y(gy), is_main(main_item) {
        radius = CELL_SIZE / 3;
        center = SDL_Point{gx * CELL_SIZE + CELL_SIZE / 2, gy * CELL_SIZE + CELL_SIZE / 2 + INFO_BAR_HEIGHT};
        rect = SDL_Rect{center.x - radius, center.y - radius, radius * 2, radius * 2};
    }
};

struct Player {
    double x{};
    double y{};
    double speed{};
    int size{};
    SDL_Rect rect{};

    Player(const GridPos& pos, double spd = PLAYER_SPEED) : x(pos.first * CELL_SIZE), y(pos.second * CELL_SIZE), speed(spd) {
        size = static_cast<int>(CELL_SIZE * 0.6);
        rect = SDL_Rect{static_cast<int>(x), static_cast<int>(y) + INFO_BAR_HEIGHT, size, size};
    }

    GridPos pos() const {
        return {static_cast<int>((x + size / 2) / CELL_SIZE), static_cast<int>((y + size / 2) / CELL_SIZE)};
    }

    void move(const Uint8* keys, const std::unordered_map<GridPos, Obstacle, PairHash>& obstacles, float dt) {
        double dx = 0.0;
        double dy = 0.0;
        if (keys[SDL_SCANCODE_W]) dy -= 1.0;
        if (keys[SDL_SCANCODE_S]) dy += 1.0;
        if (keys[SDL_SCANCODE_A]) dx -= 1.0;
        if (keys[SDL_SCANCODE_D]) dx += 1.0;
        if (dx != 0.0 && dy != 0.0) {
            dx *= 0.7071;
            dy *= 0.7071;
        }
        double nx = x + dx * speed * dt * 60.0;
        double ny = y + dy * speed * dt * 60.0;
        SDL_Rect next_rect{static_cast<int>(nx), static_cast<int>(ny) + INFO_BAR_HEIGHT, size, size};
        bool blocked = false;
        for (const auto& [_, ob] : obstacles) {
            if (ob.nonblocking) continue;
            if (SDL_HasIntersection(&next_rect, &ob.rect)) {
                blocked = true;
                break;
            }
        }
        if (!blocked && nx >= 0 && ny >= 0 && nx < WINDOW_SIZE - size && ny < WINDOW_SIZE - size) {
            x = nx;
            y = ny;
            rect.x = static_cast<int>(x);
            rect.y = static_cast<int>(y) + INFO_BAR_HEIGHT;
        }
    }
};

struct GameState;

struct Enemy {
    double x{};
    double y{};
    int attack{};
    double speed{};
    int size{};
    SDL_Rect rect{};
    std::string type;
    float attack_timer{0.0f};

    Enemy(const GridPos& pos, int atk = ENEMY_ATTACK, double spd = ENEMY_SPEED, const std::string& ztype = "basic")
        : x(pos.first * CELL_SIZE), y(pos.second * CELL_SIZE), attack(atk), speed(spd), type(ztype) {
        if (ztype == "fast") speed = std::max(speed + 1.0, speed * 1.5);
        if (ztype == "tank") attack = static_cast<int>(attack * 0.5);
        size = static_cast<int>(CELL_SIZE * 0.6);
        rect = SDL_Rect{static_cast<int>(x), static_cast<int>(y) + INFO_BAR_HEIGHT, size, size};
    }

    GridPos pos() const {
        return {static_cast<int>((x + size / 2) / CELL_SIZE), static_cast<int>((y + size / 2) / CELL_SIZE)};
    }

    void move_and_attack(const Player& player, std::vector<Obstacle>& obs_list, GameState& game_state, float attack_interval, float dt);
};

struct GameState {
    std::unordered_map<GridPos, Obstacle, PairHash> obstacles;
    std::vector<Item> items;
    int destructible_count{};
    std::vector<GridPos> main_item_pos;

    GameState() = default;
    GameState(std::unordered_map<GridPos, Obstacle, PairHash> obs,
              std::vector<Item> its,
              std::vector<GridPos> main_pos)
        : obstacles(std::move(obs)), items(std::move(its)), main_item_pos(std::move(main_pos)) {
        destructible_count = count_destructible_obstacles();
    }

    int count_destructible_obstacles() const {
        int c = 0;
        for (const auto& kv : obstacles) {
            if (kv.second.type == "Destructible") ++c;
        }
        return c;
    }

    bool collect_item(const SDL_Rect& player_rect) {
        for (auto it = items.begin(); it != items.end(); ++it) {
            if (SDL_HasIntersection(&player_rect, &it->rect)) {
                if (it->is_main) {
                    bool gate_blocked = false;
                    for (const auto& kv : obstacles) {
                        if (kv.second.is_main_block) {
                            gate_blocked = true;
                            break;
                        }
                    }
                    if (gate_blocked) return false;
                }
                items.erase(it);
                return true;
            }
        }
        return false;
    }

    void destroy_obstacle(const GridPos& pos) {
        auto it = obstacles.find(pos);
        if (it != obstacles.end()) {
            if (it->second.type == "Destructible") --destructible_count;
            obstacles.erase(it);
        }
    }
};

int sign(int v) { return v > 0 ? 1 : (v < 0 ? -1 : 0); }

float heuristic(const GridPos& a, const GridPos& b) {
    return static_cast<float>(std::abs(a.first - b.first) + std::abs(a.second - b.second));
}
std::pair<std::unordered_map<GridPos, GridPos, PairHash>, std::unordered_map<GridPos, float, PairHash>>
a_star_search(const Graph& graph, const GridPos& start, const GridPos& goal,
              const std::unordered_map<GridPos, Obstacle, PairHash>& obstacles) {
    using Node = std::pair<float, GridPos>;
    struct Cmp {
        bool operator()(const Node& a, const Node& b) const { return a.first > b.first; }
    };
    std::priority_queue<Node, std::vector<Node>, Cmp> frontier;
    frontier.push({0.0f, start});
    std::unordered_map<GridPos, GridPos, PairHash> came_from;
    std::unordered_map<GridPos, float, PairHash> cost_so_far;
    came_from[start] = start;
    cost_so_far[start] = 0.0f;
    while (!frontier.empty()) {
        auto current = frontier.top().second;
        frontier.pop();
        if (current == goal) break;
        for (const auto& neighbor : graph.neighbors(current)) {
            float new_cost = cost_so_far[current] + graph.cost(current, neighbor);
            auto it = obstacles.find(neighbor);
            if (it != obstacles.end()) {
                if (it->second.type == "Indestructible") continue;
                if (it->second.type == "Destructible") {
                    float k_factor = std::ceil(it->second.health / static_cast<float>(ENEMY_ATTACK)) * 0.1f;
                    new_cost = cost_so_far[current] + 1.0f + k_factor;
                }
            }
            if (!cost_so_far.count(neighbor) || new_cost < cost_so_far[neighbor]) {
                cost_so_far[neighbor] = new_cost;
                float priority = new_cost + heuristic(goal, neighbor);
                frontier.push({priority, neighbor});
                came_from[neighbor] = current;
            }
        }
    }
    return {came_from, cost_so_far};
}

bool is_not_edge(const GridPos& pos, int grid_size) {
    return pos.first >= 1 && pos.first < grid_size - 1 && pos.second >= 1 && pos.second < grid_size - 1;
}

std::vector<GridPos> reconstruct_path(const std::unordered_map<GridPos, GridPos, PairHash>& came_from,
                                      const GridPos& start,
                                      const GridPos& goal) {
    std::vector<GridPos> path;
    auto it = came_from.find(goal);
    if (it == came_from.end()) {
        path.push_back(start);
        return path;
    }
    GridPos current = goal;
    while (current != start) {
        path.push_back(current);
        current = came_from.at(current);
    }
    path.push_back(start);
    std::reverse(path.begin(), path.end());
    return path;
}

struct LevelConfig {
    int obstacle_count{};
    int item_count{};
    int enemy_count{};
    int block_hp{};
    std::vector<std::string> enemy_types;
    std::string reward;
};

const std::vector<std::string> CARD_POOL = {
    "enemy_fast", "enemy_strong", "enemy_tank", "enemy_spitter", "enemy_leech"
};

const std::vector<LevelConfig> BASE_LEVELS = {
    {15, 3, 1, 10, {"basic"}, "enemy_fast"},
    {18, 4, 2, 15, {"basic", "strong"}, "enemy_strong"}
};

LevelConfig get_level_config(int level) {
    if (level < static_cast<int>(BASE_LEVELS.size())) {
        return BASE_LEVELS[level];
    }
    LevelConfig cfg;
    cfg.obstacle_count = 20 + level;
    cfg.item_count = 5;
    cfg.enemy_count = std::min(5, 1 + level / 3);
    cfg.block_hp = static_cast<int>(10 * std::pow(1.2, level - static_cast<int>(BASE_LEVELS.size()) + 1));
    cfg.enemy_types = {"basic", "strong", "fire"};
    cfg.reward = CARD_POOL[rand_int(0, static_cast<int>(CARD_POOL.size()) - 1)];
    return cfg;
}

std::tuple<std::unordered_map<GridPos, Obstacle, PairHash>, std::vector<Item>, GridPos, std::vector<GridPos>, std::vector<GridPos>>
generate_game_entities(int grid_size, int obstacle_count, int item_count, int enemy_count, int main_block_hp) {
    std::vector<GridPos> all_positions;
    all_positions.reserve(grid_size * grid_size);
    for (int x = 0; x < grid_size; ++x) {
        for (int y = 0; y < grid_size; ++y) {
            all_positions.emplace_back(x, y);
        }
    }
    std::unordered_set<GridPos, PairHash> forbidden;
    forbidden.insert({0, 0});
    forbidden.insert({0, grid_size - 1});
    forbidden.insert({grid_size - 1, 0});
    forbidden.insert({grid_size - 1, grid_size - 1});

    auto pick_valid_positions = [&](int min_distance, int count) {
        GridPos player_pos{0, 0};
        std::vector<GridPos> enemies;
        while (true) {
            std::vector<GridPos> picks = all_positions;
            std::shuffle(picks.begin(), picks.end(), rng);
            picks.resize(static_cast<std::size_t>(count + 1));
            player_pos = picks[0];
            enemies.assign(picks.begin() + 1, picks.end());
            bool ok = true;
            for (const auto& e : enemies) {
                if (std::abs(player_pos.first - e.first) + std::abs(player_pos.second - e.second) < min_distance) {
                    ok = false;
                    break;
                }
            }
            if (ok) break;
        }
        return std::make_pair(player_pos, enemies);
    };

    auto [player_pos, enemy_pos_list] = pick_valid_positions(5, enemy_count);
    forbidden.insert(player_pos);
    for (const auto& pos : enemy_pos_list) forbidden.insert(pos);

    std::vector<GridPos> main_item_candidates;
    for (const auto& p : all_positions) {
        if (!forbidden.count(p) && is_not_edge(p, grid_size)) {
            main_item_candidates.push_back(p);
        }
    }
    GridPos main_item_pos = main_item_candidates[rand_int(0, static_cast<int>(main_item_candidates.size()) - 1)];
    forbidden.insert(main_item_pos);

    std::unordered_map<GridPos, Obstacle, PairHash> obstacles;
    Obstacle main_block(main_item_pos.first, main_item_pos.second, "Destructible", main_block_hp);
    main_block.is_main_block = true;
    obstacles.emplace(main_item_pos, main_block);
    std::vector<GridPos> rest_candidates;
    for (const auto& p : all_positions) {
        if (!forbidden.count(p)) rest_candidates.push_back(p);
    }
    int rest_count = obstacle_count - 1;
    if (rest_count < 0) rest_count = 0;
    if (rest_count > static_cast<int>(rest_candidates.size())) rest_count = static_cast<int>(rest_candidates.size());
    std::shuffle(rest_candidates.begin(), rest_candidates.end(), rng);
    rest_candidates.resize(rest_count);
    int destructible_count = static_cast<int>(rest_count * DESTRUCTIBLE_RATIO);
    for (int i = 0; i < rest_count; ++i) {
        const auto& pos = rest_candidates[static_cast<std::size_t>(i)];
        if (i < destructible_count) {
            obstacles.emplace(pos, Obstacle(pos.first, pos.second, "Destructible", OBSTACLE_HEALTH));
        } else {
            obstacles.emplace(pos, Obstacle(pos.first, pos.second, "Indestructible"));
        }
    }
    for (const auto& p : rest_candidates) forbidden.insert(p);

    std::vector<GridPos> item_candidates;
    for (const auto& p : all_positions) {
        if (!forbidden.count(p)) item_candidates.push_back(p);
    }
    if (item_count < 1) item_count = 1;
    if (item_count > static_cast<int>(item_candidates.size())) item_count = static_cast<int>(item_candidates.size());
    std::shuffle(item_candidates.begin(), item_candidates.end(), rng);
    item_candidates.resize(static_cast<std::size_t>(item_count - 1));

    std::vector<Item> items;
    for (const auto& p : item_candidates) {
        items.emplace_back(p.first, p.second, false);
    }
    items.emplace_back(main_item_pos.first, main_item_pos.second, true);
    std::vector<GridPos> main_item_list = {main_item_pos};

    return {std::move(obstacles), std::move(items), player_pos, enemy_pos_list, main_item_list};
}

Graph build_graph(int grid_size, const std::unordered_map<GridPos, Obstacle, PairHash>& obstacles) {
    Graph graph;
    for (int x = 0; x < grid_size; ++x) {
        for (int y = 0; y < grid_size; ++y) {
            GridPos current{x, y};
            auto it = obstacles.find(current);
            if (it != obstacles.end() && it->second.type == "Indestructible") continue;
            const std::array<GridPos, 4> dirs = {{{-1, 0}, {1, 0}, {0, -1}, {0, 1}}};
            for (const auto& d : dirs) {
                GridPos neighbor{x + d.first, y + d.second};
                if (neighbor.first < 0 || neighbor.second < 0 || neighbor.first >= grid_size || neighbor.second >= grid_size) continue;
                auto ob = obstacles.find(neighbor);
                if (ob != obstacles.end() && ob->second.type == "Indestructible") continue;
                float weight = 1.0f;
                if (ob != obstacles.end() && ob->second.type == "Destructible") weight = 10.0f;
                graph.add_edge(current, neighbor, weight);
            }
        }
    }
    return graph;
}

SDL_Texture* capture_frame(SDL_Renderer* renderer) {
    int w, h;
    if (SDL_GetRendererOutputSize(renderer, &w, &h) != 0) return nullptr;
    SDL_Surface* surf = SDL_CreateRGBSurfaceWithFormat(0, w, h, 32, SDL_PIXELFORMAT_ARGB8888);
    if (!surf) return nullptr;
    if (SDL_RenderReadPixels(renderer, nullptr, surf->format->format, surf->pixels, surf->pitch) != 0) {
        SDL_FreeSurface(surf);
        return nullptr;
    }
    SDL_Texture* tex = SDL_CreateTextureFromSurface(renderer, surf);
    SDL_FreeSurface(surf);
    return tex;
}
SDL_Texture* render_game(SDL_Renderer* renderer, const GameState& game_state, const Player& player, const std::vector<Enemy>& enemies) {
    SDL_SetRenderDrawColor(renderer, 20, 20, 20, 255);
    SDL_RenderClear(renderer);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_Rect bar{0, 0, WINDOW_SIZE, INFO_BAR_HEIGHT};
    SDL_RenderFillRect(renderer, &bar);
    draw_text(renderer, "ITEMS: " + std::to_string(game_state.items.size()), 24, {255, 255, 80, 255}, 12, 12);

    SDL_SetRenderDrawColor(renderer, 50, 50, 50, 255);
    for (int y = 0; y < GRID_SIZE; ++y) {
        for (int x = 0; x < GRID_SIZE; ++x) {
            SDL_Rect cell{x * CELL_SIZE, y * CELL_SIZE + INFO_BAR_HEIGHT, CELL_SIZE, CELL_SIZE};
            SDL_RenderDrawRect(renderer, &cell);
        }
    }
    for (const auto& item : game_state.items) {
        SDL_Color c = item.is_main ? SDL_Color{255, 255, 100, 255} : SDL_Color{255, 255, 0, 255};
        SDL_SetRenderDrawColor(renderer, c.r, c.g, c.b, 255);
        for (int rx = -item.radius; rx <= item.radius; ++rx) {
            for (int ry = -item.radius; ry <= item.radius; ++ry) {
                if (rx * rx + ry * ry <= item.radius * item.radius) {
                    SDL_RenderDrawPoint(renderer, item.center.x + rx, item.center.y + ry);
                }
            }
        }
    }

    SDL_SetRenderDrawColor(renderer, 0, 255, 0, 255);
    SDL_RenderFillRect(renderer, &player.rect);

    SDL_SetRenderDrawColor(renderer, 255, 60, 60, 255);
    for (const auto& enemy : enemies) {
        SDL_RenderFillRect(renderer, &enemy.rect);
    }

    for (const auto& kv : game_state.obstacles) {
        const auto& obstacle = kv.second;
        bool is_main = obstacle.is_main_block;
        SDL_Color c;
        if (is_main) c = {255, 220, 80, 255};
        else if (obstacle.type == "Indestructible") c = {120, 120, 120, 255};
        else c = {200, 80, 80, 255};
        SDL_SetRenderDrawColor(renderer, c.r, c.g, c.b, 255);
        SDL_RenderFillRect(renderer, &obstacle.rect);
        if (obstacle.type == "Destructible") {
            draw_text(renderer, std::to_string(obstacle.health), 20, {255, 255, 255, 255},
                      obstacle.rect.x + 6, obstacle.rect.y + 8);
        }
    }
    SDL_RenderPresent(renderer);
    return capture_frame(renderer);
}

void Enemy::move_and_attack(const Player& player, std::vector<Obstacle>& obs_list, GameState& game_state, float attack_interval, float dt) {
    attack_timer += dt;
    double dx = player.x - x;
    double dy = player.y - y;
    double spd = speed * dt * 60.0;
    std::vector<GridPos> dirs;
    if (std::abs(dx) > std::abs(dy)) {
        dirs = {{sign(static_cast<int>(dx)), 0}, {0, sign(static_cast<int>(dy))},
                {sign(static_cast<int>(dx)), sign(static_cast<int>(dy))},
                {-sign(static_cast<int>(dx)), 0}, {0, -sign(static_cast<int>(dy))}};
    } else {
        dirs = {{0, sign(static_cast<int>(dy))}, {sign(static_cast<int>(dx)), 0},
                {sign(static_cast<int>(dx)), sign(static_cast<int>(dy))},
                {0, -sign(static_cast<int>(dy))}, {-sign(static_cast<int>(dx)), 0}};
    }
    for (const auto& d : dirs) {
        if (d.first == 0 && d.second == 0) continue;
        SDL_Rect next_rect = rect;
        next_rect.x += static_cast<int>(d.first * spd);
        next_rect.y += static_cast<int>(d.second * spd);
        bool blocked = false;
        for (auto it = obs_list.begin(); it != obs_list.end(); ++it) {
            if (it->nonblocking) continue;
            if (SDL_HasIntersection(&next_rect, &it->rect)) {
                if (it->type == "Destructible") {
                    if (attack_timer >= attack_interval) {
                        it->health -= attack;
                        attack_timer = 0.0f;
                        if (it->health <= 0) {
                            GridPos gp = it->grid_pos();
                            game_state.destroy_obstacle(gp);
                            obs_list.erase(it);
                        }
                    }
                }
                blocked = true;
                break;
            }
        }
        if (!blocked) {
            x += d.first * spd;
            y += d.second * spd;
            rect.x = static_cast<int>(x);
            rect.y = static_cast<int>(y) + INFO_BAR_HEIGHT;
            break;
        }
    }
}
std::string show_help(SDL_Renderer* renderer) {
    SDL_Event e;
    Uint32 last = SDL_GetTicks();
    while (true) {
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT) return "quit";
            if (e.type == SDL_MOUSEBUTTONDOWN) {
                SDL_Point p{e.button.x, e.button.y};
                SDL_Rect back_btn = draw_button(renderer, "BACK", WINDOW_SIZE / 2 - 90, TOTAL_HEIGHT - 120);
                if (point_in_rect(back_btn, p.x, p.y)) {
                    door_transition(renderer);
                    return "back";
                }
            }
        }
        SDL_SetRenderDrawColor(renderer, 18, 18, 18, 255);
        SDL_RenderClear(renderer);
        draw_text(renderer, "How to Play", 40, {240, 240, 240, 255}, 40, 40);
        const std::array<std::string, 5> lines = {
            "WASD to move. Collect all memory fragments to win.",
            "Breakable yellow blocks guard the final fragment.",
            "Enemies chase you. Touch = defeat.",
            "After each win: pick an enemy card as reward.",
            "Before next level: choose which enemy type spawns."
        };
        int y = 100;
        for (const auto& s : lines) {
            draw_text(renderer, s, 24, {200, 200, 200, 255}, 40, y);
            y += 36;
        }
        draw_button(renderer, "BACK", WINDOW_SIZE / 2 - 90, TOTAL_HEIGHT - 120);
        SDL_RenderPresent(renderer);
        Uint32 now = SDL_GetTicks();
        if (now - last < 16) SDL_Delay(16 - (now - last));
    }
}

bool show_start_menu(SDL_Renderer* renderer) {
    SDL_Event e;
    Uint32 last = SDL_GetTicks();
    while (true) {
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT) return false;
            if (e.type == SDL_MOUSEBUTTONDOWN) {
                SDL_Point p{e.button.x, e.button.y};
                SDL_Rect start_rect = draw_button(renderer, "START", WINDOW_SIZE / 2 - 200, 260);
                SDL_Rect how_rect = draw_button(renderer, "HOW TO PLAY", WINDOW_SIZE / 2 + 20, 260);
                SDL_Rect exit_rect = draw_button(renderer, "EXIT", WINDOW_SIZE / 2 - 90, 340);
                if (point_in_rect(start_rect, p.x, p.y)) {
                    door_transition(renderer);
                    return true;
                }
                if (point_in_rect(exit_rect, p.x, p.y)) return false;
                if (point_in_rect(how_rect, p.x, p.y)) {
                    show_help(renderer);
                }
            }
        }
        SDL_SetRenderDrawColor(renderer, 26, 28, 24, 255);
        SDL_RenderClear(renderer);
        for (int i = 0; i < WINDOW_SIZE; i += 40) {
            SDL_Rect r{i, 0, 40, TOTAL_HEIGHT};
            int shade = (i / 40 % 2) ? 38 : 32;
            SDL_SetRenderDrawColor(renderer, shade, 34, 30, 255);
            SDL_RenderFillRect(renderer, &r);
        }
        draw_text(renderer, GAME_TITLE, 64, {230, 230, 210, 255}, WINDOW_SIZE / 2 - 200, 120);
        draw_text(renderer, "A pixel roguelite of memory and monsters", 24, {160, 160, 150, 255}, WINDOW_SIZE / 2 - 260, 180);
        draw_button(renderer, "START", WINDOW_SIZE / 2 - 200, 260);
        draw_button(renderer, "HOW TO PLAY", WINDOW_SIZE / 2 + 20, 260);
        draw_button(renderer, "EXIT", WINDOW_SIZE / 2 - 90, 340);
        SDL_RenderPresent(renderer);
        Uint32 now = SDL_GetTicks();
        if (now - last < 16) SDL_Delay(16 - (now - last));
    }
}
std::string show_fail_screen(SDL_Renderer* renderer, SDL_Texture* background) {
    SDL_Event e;
    Uint32 last = SDL_GetTicks();
    while (true) {
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT) return "exit";
            if (e.type == SDL_MOUSEBUTTONDOWN) {
                SDL_Point p{e.button.x, e.button.y};
                SDL_Rect retry = draw_button(renderer, "RETRY", WINDOW_SIZE / 2 - 200, 300);
                SDL_Rect home = draw_button(renderer, "HOME", WINDOW_SIZE / 2 + 20, 300);
                if (point_in_rect(retry, p.x, p.y)) {
                    door_transition(renderer);
                    return "retry";
                }
                if (point_in_rect(home, p.x, p.y)) {
                    door_transition(renderer);
                    return "home";
                }
            }
        }
        if (background) {
            SDL_RenderCopy(renderer, background, nullptr, nullptr);
            SDL_SetRenderDrawColor(renderer, 0, 0, 0, 180);
            SDL_Rect dim{0, 0, WINDOW_SIZE, TOTAL_HEIGHT};
            SDL_RenderFillRect(renderer, &dim);
        } else {
            SDL_SetRenderDrawColor(renderer, 0, 0, 0, 200);
            SDL_RenderClear(renderer);
        }
        draw_text(renderer, "YOU WERE CORRUPTED!", 80, {255, 60, 60, 255}, WINDOW_SIZE / 2 - 320, 140);
        draw_button(renderer, "RETRY", WINDOW_SIZE / 2 - 200, 300);
        draw_button(renderer, "HOME", WINDOW_SIZE / 2 + 20, 300);
        SDL_RenderPresent(renderer);
        Uint32 now = SDL_GetTicks();
        if (now - last < 16) SDL_Delay(16 - (now - last));
    }
}

std::string show_success_screen(SDL_Renderer* renderer, SDL_Texture* background, const std::vector<std::string>& reward_choices) {
    SDL_Event e;
    Uint32 last = SDL_GetTicks();
    std::string chosen;
    while (true) {
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT) return "exit";
            if (e.type == SDL_MOUSEBUTTONDOWN) {
                SDL_Point p{e.button.x, e.button.y};
                int idx = 0;
                for (const auto& card : reward_choices) {
                    int x = WINDOW_SIZE / 2 - (static_cast<int>(reward_choices.size()) * 140) / 2 + idx * 140;
                    SDL_Rect rect{x, 180, 120, 160};
                    if (point_in_rect(rect, p.x, p.y)) chosen = card;
                    ++idx;
                }
                SDL_Rect next_btn = draw_button(renderer, "CONFIRM", WINDOW_SIZE / 2 - 90, 370);
                if (point_in_rect(next_btn, p.x, p.y) && (!reward_choices.empty())) {
                    door_transition(renderer);
                    return chosen.empty() ? reward_choices.front() : chosen;
                }
            }
        }
        if (background) {
            SDL_RenderCopy(renderer, background, nullptr, nullptr);
            SDL_SetRenderDrawColor(renderer, 0, 0, 0, 150);
            SDL_Rect dim{0, 0, WINDOW_SIZE, TOTAL_HEIGHT};
            SDL_RenderFillRect(renderer, &dim);
        } else {
            SDL_SetRenderDrawColor(renderer, 0, 0, 0, 200);
            SDL_RenderClear(renderer);
        }
        draw_text(renderer, "MEMORY RESTORED!", 80, {0, 255, 120, 255}, WINDOW_SIZE / 2 - 320, 100);
        int idx = 0;
        for (const auto& card : reward_choices) {
            int x = WINDOW_SIZE / 2 - (static_cast<int>(reward_choices.size()) * 140) / 2 + idx * 140;
            SDL_Rect rect{x, 180, 120, 160};
            SDL_SetRenderDrawColor(renderer, 220, 220, 220, 255);
            SDL_RenderFillRect(renderer, &rect);
            draw_text(renderer, card, 24, {20, 20, 20, 255}, rect.x + 10, rect.y + rect.h - 30);
            SDL_SetRenderDrawColor(renderer, 40, 40, 40, 255);
            SDL_RenderDrawRect(renderer, &rect);
            ++idx;
        }
        draw_button(renderer, "CONFIRM", WINDOW_SIZE / 2 - 90, 370);
        SDL_RenderPresent(renderer);
        Uint32 now = SDL_GetTicks();
        if (now - last < 16) SDL_Delay(16 - (now - last));
    }
}

std::string select_enemy_screen(SDL_Renderer* renderer, const std::vector<std::string>& owned_cards) {
    if (owned_cards.empty()) return "basic";
    SDL_Event e;
    Uint32 last = SDL_GetTicks();
    std::string chosen;
    while (true) {
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT) return "basic";
            if (e.type == SDL_MOUSEBUTTONDOWN) {
                SDL_Point p{e.button.x, e.button.y};
                int idx = 0;
                for (const auto& card : owned_cards) {
                    int x = WINDOW_SIZE / 2 - (static_cast<int>(owned_cards.size()) * 140) / 2 + idx * 140;
                    SDL_Rect rect{x, 180, 120, 160};
                    if (point_in_rect(rect, p.x, p.y)) chosen = card;
                    ++idx;
                }
                SDL_Rect confirm = draw_button(renderer, "CONFIRM", WINDOW_SIZE / 2 - 90, 370);
                if (point_in_rect(confirm, p.x, p.y)) {
                    door_transition(renderer);
                    return chosen.empty() ? owned_cards.front() : chosen;
                }
            }
        }
        SDL_SetRenderDrawColor(renderer, 18, 18, 18, 255);
        SDL_RenderClear(renderer);
        draw_text(renderer, "Choose Next Level's Enemy", 48, {230, 230, 230, 255}, WINDOW_SIZE / 2 - 260, 110);
        int idx = 0;
        for (const auto& card : owned_cards) {
            int x = WINDOW_SIZE / 2 - (static_cast<int>(owned_cards.size()) * 140) / 2 + idx * 140;
            SDL_Rect rect{x, 180, 120, 160};
            SDL_SetRenderDrawColor(renderer, 200, 200, 200, 255);
            SDL_RenderFillRect(renderer, &rect);
            draw_text(renderer, card, 24, {30, 30, 30, 255}, rect.x + 8, rect.y + rect.h - 30);
            SDL_SetRenderDrawColor(renderer, 40, 40, 40, 255);
            SDL_RenderDrawRect(renderer, &rect);
            ++idx;
        }
        draw_button(renderer, "CONFIRM", WINDOW_SIZE / 2 - 90, 370);
        SDL_RenderPresent(renderer);
        Uint32 now = SDL_GetTicks();
        if (now - last < 16) SDL_Delay(16 - (now - last));
    }
}
struct LevelResult {
    std::string result;
    std::optional<std::string> reward;
    SDL_Texture* frame;
};

LevelResult main_run_level(SDL_Renderer* renderer, const LevelConfig& config, const std::string& chosen_enemy) {
    auto [obs_map, items, player_start, enemy_starts, main_item_list] = generate_game_entities(
        GRID_SIZE, config.obstacle_count, config.item_count, config.enemy_count, config.block_hp);
    GameState game_state(std::move(obs_map), std::move(items), std::move(main_item_list));
    Player player(player_start, PLAYER_SPEED);

    std::unordered_map<std::string, std::string> ztype_map = {
        {"enemy_fast", "fast"},
        {"enemy_tank", "tank"},
        {"enemy_strong", "strong"},
        {"enemy_spitter", "spitter"},
        {"enemy_leech", "leech"},
        {"basic", "basic"}
    };
    std::string zt = ztype_map.count(chosen_enemy) ? ztype_map[chosen_enemy] : "basic";
    std::vector<Enemy> enemies;
    enemies.reserve(enemy_starts.size());
    for (const auto& pos : enemy_starts) {
        enemies.emplace_back(pos, ENEMY_ATTACK, ENEMY_SPEED, zt);
    }

    bool running = true;
    std::string game_result;
    SDL_Texture* last_frame = nullptr;
    Uint32 previous = SDL_GetTicks();

    while (running) {
        Uint32 now = SDL_GetTicks();
        float dt = (now - previous) / 1000.0f;
        previous = now;
        SDL_Event e;
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT) {
                return {"exit", std::nullopt, last_frame};
            }
        }
        const Uint8* keys = SDL_GetKeyboardState(nullptr);
        player.move(keys, game_state.obstacles, dt);
        game_state.collect_item(player.rect);
        std::vector<Obstacle> obs_list;
        obs_list.reserve(game_state.obstacles.size());
        for (const auto& kv : game_state.obstacles) obs_list.push_back(kv.second);

        for (auto& enemy : enemies) {
            enemy.move_and_attack(player, obs_list, game_state, 0.5f, dt);
            SDL_Rect player_rect{static_cast<int>(player.x), static_cast<int>(player.y) + INFO_BAR_HEIGHT, player.size, player.size};
            if (SDL_HasIntersection(&enemy.rect, &player_rect)) {
                game_result = "fail";
                running = false;
                break;
            }
        }
        if (!running) break;
        if (game_state.items.empty()) {
            game_result = "success";
            running = false;
        }
        SDL_DestroyTexture(last_frame);
        last_frame = render_game(renderer, game_state, player, enemies);
        Uint32 frame_time = SDL_GetTicks() - now;
        if (frame_time < 16) SDL_Delay(16 - frame_time);
    }
    return {game_result, config.reward, last_frame};
}
int main(int argc, char** argv) {
    (void)argc; (void)argv;
    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        SDL_Log("SDL_Init failed: %s", SDL_GetError());
        return 1;
    }
    if (TTF_Init() != 0) {
        SDL_Log("TTF_Init failed: %s", TTF_GetError());
        SDL_Quit();
        return 1;
    }
    SDL_Window* window = SDL_CreateWindow(
        GAME_TITLE,
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        WINDOW_SIZE, TOTAL_HEIGHT,
        SDL_WINDOW_SHOWN);
    if (!window) {
        SDL_Log("Failed to create window: %s", SDL_GetError());
        TTF_Quit();
        SDL_Quit();
        return 1;
    }
    SDL_Renderer* renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!renderer) {
        SDL_Log("Failed to create renderer: %s", SDL_GetError());
        SDL_DestroyWindow(window);
        TTF_Quit();
        SDL_Quit();
        return 1;
    }

    bool started = show_start_menu(renderer);
    if (!started) {
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        TTF_Quit();
        SDL_Quit();
        return 0;
    }

    int current_level = 0;
    std::vector<std::string> enemy_cards_collected;

    while (true) {
        LevelConfig config = get_level_config(current_level);
        std::string chosen_enemy = enemy_cards_collected.empty() ? "basic" : select_enemy_screen(renderer, enemy_cards_collected);
        door_transition(renderer);
        LevelResult result = main_run_level(renderer, config, chosen_enemy);
        SDL_Texture* bg = result.frame;
        if (result.result == "fail") {
            std::string action = show_fail_screen(renderer, bg);
            SDL_DestroyTexture(bg);
            if (action == "home") {
                bool again = show_start_menu(renderer);
                if (!again) break;
                current_level = 0;
                enemy_cards_collected.clear();
            } else if (action == "retry") {
                continue;
            } else {
                break;
            }
        } else if (result.result == "success") {
            std::vector<std::string> pool;
            for (const auto& card : CARD_POOL) {
                if (std::find(enemy_cards_collected.begin(), enemy_cards_collected.end(), card) == enemy_cards_collected.end()) {
                    pool.push_back(card);
                }
            }
            std::vector<std::string> reward_choices;
            if (!pool.empty()) {
                std::shuffle(pool.begin(), pool.end(), rng);
                int k = std::min(3, static_cast<int>(pool.size()));
                reward_choices.assign(pool.begin(), pool.begin() + k);
            }
            std::string chosen = show_success_screen(renderer, bg, reward_choices);
            SDL_DestroyTexture(bg);
            if (!chosen.empty()) enemy_cards_collected.push_back(chosen);
            current_level += 1;
        } else {
            SDL_DestroyTexture(bg);
            break;
        }
    }

    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    TTF_Quit();
    SDL_Quit();
    return 0;
}
