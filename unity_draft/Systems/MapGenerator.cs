using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Lightweight procedural placement for obstacles, decor, and items.
    /// Mirrors the Python generate_game_entities intent with an ensure_passage_budget check.
    /// </summary>
    public class MapGenerator : MonoBehaviour
    {
        [Header("Refs")]
        public GameBalanceConfig balance;
        public GridManager gridManager;
        public Transform obstaclesRoot;
        public Transform decorRoot;
        public Transform itemsRoot;

        [Header("Prefabs")]
        public GameObject obstaclePrefab;
        public GameObject destructiblePrefab;
        public GameObject decorPrefab;
        public GameObject coinPrefab;
        public GameObject itemPickupPrefab;
        public ObstacleSet obstacleSet;
        public ItemCatalog itemCatalog;

        [Header("Counts")]
        public int obstacleCount = 40;
        public int destructibleCount = 10;
        public int decorCount = 20;
        public int itemPickupCount = 8;
        public DestructibleLootTable destructibleLoot;

        [Header("Placement")]
        public float innerRadius = 4f; // keep spawn clear near player center
        public float mapRadius = 18f;
        public float minObstacleSpacing = 1.2f;
        [Tooltip("Ensure corridors from center to edges by carving if needed.")]
        public bool ensurePassage = true;
        [Tooltip("Carve an orthogonal cross from center to edges.")]
        public bool carveCross = true;
        [Tooltip("Extra random corridors carved if cross isn't enough.")]
        public int extraCorridors = 2;
        [Tooltip("Corridor half-width in grid cells.")]
        public int corridorWidthCells = 1;

        private readonly List<Vector2> _placed = new();
        private readonly Dictionary<Vector2Int, GameObject> _obstacleLookup = new();

        private void OnEnable()
        {
            if (gridManager == null) gridManager = FindObjectOfType<GridManager>();
        }

        public void Generate(Vector3 center)
        {
            if (gridManager == null) gridManager = FindObjectOfType<GridManager>();
            _placed.Clear();
            _obstacleLookup.Clear();
            PlaceBatch(obstaclePrefab, obstacleCount, center, obstaclesRoot, solid:true, destructible:false);
            PlaceBatch(destructiblePrefab, destructibleCount, center, obstaclesRoot, solid:true, destructible:true);
            PlaceBatch(decorPrefab, decorCount, center, decorRoot, solid:false, destructible:false);
            PlaceItems(itemPickupPrefab, itemPickupCount, center, itemsRoot);
            PlaceCoins(coinPrefab, Mathf.CeilToInt(itemPickupCount * 0.5f), center, itemsRoot);
            gridManager?.BuildBlockedGrid();
            if (ensurePassage && gridManager != null) EnsurePassages(center);
        }

        private GameObject PickFromSet(GameObject fallback, GameObject[] set)
        {
            if (set != null && set.Length > 0)
            {
                return set[Random.Range(0, set.Length)];
            }
            return fallback;
        }

        private void PlaceBatch(GameObject prefab, int count, Vector3 center, Transform parent, bool solid, bool destructible)
        {
            if (prefab == null || count <= 0) return;
            for (int i = 0; i < count; i++)
            {
                Vector3 pos;
                if (!TryFindSpot(center, out pos)) continue;
                GameObject chosen = prefab;
                if (obstacleSet != null)
                {
                    if (solid && !destructible) chosen = PickFromSet(prefab, obstacleSet.solids);
                    if (solid && destructible) chosen = PickFromSet(destructiblePrefab, obstacleSet.destructibles);
                    if (!solid) chosen = PickFromSet(decorPrefab, obstacleSet.decor);
                }
                var go = Instantiate(chosen, pos, Quaternion.identity, parent);
                _placed.Add(pos);
                if (solid && gridManager != null)
                {
                    gridManager.AddObstacle(pos, 0);
                    var cell = gridManager.WorldToGrid(pos);
                    if (!_obstacleLookup.ContainsKey(cell))
                    {
                        _obstacleLookup.Add(cell, go);
                    }
                }
                if (destructible)
                {
                    var d = go.GetComponent<DestructibleObstacle>();
                    if (d == null) d = go.AddComponent<DestructibleObstacle>();
                    d.gridManager = gridManager;
                    d.lootTable = destructibleLoot;
                }
            }
        }

        private void PlaceItems(GameObject prefab, int count, Vector3 center, Transform parent)
        {
            if ((prefab == null && itemCatalog == null) || count <= 0) return;
            for (int i = 0; i < count; i++)
            {
                if (!TryFindSpot(center, out var pos)) continue;
                GameObject chosen = prefab;
                ItemPickupDef def = null;
                if (itemCatalog != null && itemCatalog.items.Count > 0)
                {
                    def = PickItemDef();
                    if (def != null && def.prefab != null) chosen = def.prefab;
                }
                var go = Instantiate(chosen, pos, Quaternion.identity, parent);
                if (def != null)
                {
                    var ip = go.GetComponent<ItemPickup>() ?? go.AddComponent<ItemPickup>();
                    ip.type = def.type;
                    ip.amount = def.amount;
                    ip.consumableId = def.consumableId;
                    ip.consumableCount = def.consumableCount;
                }
            }
        }

        private void PlaceCoins(GameObject prefab, int count, Vector3 center, Transform parent)
        {
            if (prefab == null || count <= 0) return;
            for (int i = 0; i < count; i++)
            {
                if (!TryFindSpot(center, out var pos)) continue;
                Instantiate(prefab, pos, Quaternion.identity, parent);
            }
        }

        private bool TryFindSpot(Vector3 center, out Vector3 pos)
        {
            int attempts = 32;
            float clearRadius = balance != null ? balance.navClearRadiusPx : 1f;
            while (attempts-- > 0)
            {
                float r = Random.Range(innerRadius, mapRadius);
                float ang = Random.Range(0f, Mathf.PI * 2f);
                Vector3 p = center + new Vector3(Mathf.Cos(ang), Mathf.Sin(ang), 0f) * r;
                if (IsClear(p, clearRadius))
                {
                    pos = p;
                    return true;
                }
            }
            pos = Vector3.zero;
            return false;
        }

        private bool IsClear(Vector3 pos, float radius)
        {
            foreach (var p in _placed)
            {
                float minDist = Mathf.Max(minObstacleSpacing, radius / Mathf.Max(0.001f, balance != null ? balance.cellSize : 1f));
                if ((p - (Vector2)pos).sqrMagnitude < minDist * minDist) return false;
            }
            if (gridManager != null)
            {
                // ensure passage clearance
                if (gridManager.IsBlocked(pos)) return false;
                if (balance != null && !gridManager.IsClearWithRadius(pos, balance.navClearRadiusPx))
                    return false;
            }
            return true;
        }

        private void EnsurePassages(Vector3 center)
        {
            int n = balance != null ? balance.gridSize : 32;
            float cs = balance != null ? balance.cellSize : 1f;
            var start = gridManager.WorldToGrid(center);
            var goals = new List<Vector2Int>
            {
                new Vector2Int(start.x, 0),
                new Vector2Int(start.x, n-1),
                new Vector2Int(0, start.y),
                new Vector2Int(n-1, start.y),
            };
            if (carveCross)
            {
                CarveLine(new Vector2Int(0, start.y), new Vector2Int(n - 1, start.y));
                CarveLine(new Vector2Int(start.x, 0), new Vector2Int(start.x, n - 1));
            }
            for (int i = 0; i < extraCorridors; i++)
            {
                var a = new Vector2Int(Random.Range(0, n), Random.Range(0, n));
                var b = new Vector2Int(Random.Range(0, n), Random.Range(0, n));
                CarveLine(a, b);
            }
            var blocked = gridManager.BuildBlockedGrid();
            foreach (var g in goals)
            {
                var path = Pathfinding.GridPathfinder.FindPath(blocked, start, g);
                if (path == null)
                {
                    CarveCorridor(blocked, start, g);
                }
            }
            gridManager.BuildBlockedGrid();
        }

        private void CarveCorridor(bool[,] blocked, Vector2Int start, Vector2Int goal)
        {
            var line = Bresenham(start, goal);
            foreach (var cell in line)
            {
                if (_obstacleLookup.TryGetValue(cell, out var go))
                {
                    if (go != null) Destroy(go);
                    _obstacleLookup.Remove(cell);
                }
                CarveCell(cell, blocked);
            }
        }

        private void CarveLine(Vector2Int a, Vector2Int b)
        {
            int n = balance != null ? balance.gridSize : 32;
            bool[,] dummy = new bool[n, n];
            CarveCorridor(dummy, a, b);
        }

        private void CarveCell(Vector2Int cell, bool[,] blocked)
        {
            for (int dx = -corridorWidthCells; dx <= corridorWidthCells; dx++)
            {
                for (int dy = -corridorWidthCells; dy <= corridorWidthCells; dy++)
                {
                    var c = new Vector2Int(cell.x + dx, cell.y + dy);
                    if (blocked != null)
                    {
                        if (c.x >= 0 && c.x < blocked.GetLength(0) && c.y >= 0 && c.y < blocked.GetLength(1))
                            blocked[c.x, c.y] = false;
                    }
                    gridManager.RemoveObstacle(c);
                    _obstacleLookup.Remove(c);
                }
            }
        }

        private List<Vector2Int> Bresenham(Vector2Int a, Vector2Int b)
        {
            List<Vector2Int> pts = new();
            int dx = Mathf.Abs(b.x - a.x);
            int dy = Mathf.Abs(b.y - a.y);
            int sx = a.x < b.x ? 1 : -1;
            int sy = a.y < b.y ? 1 : -1;
            int err = dx - dy;
            int x = a.x;
            int y = a.y;
            while (true)
            {
                pts.Add(new Vector2Int(x, y));
                if (x == b.x && y == b.y) break;
                int e2 = 2 * err;
                if (e2 > -dy)
                {
                    err -= dy;
                    x += sx;
                }
                if (e2 < dx)
                {
                    err += dx;
                    y += sy;
                }
            }
            return pts;
        }

        private ItemPickupDef PickItemDef()
        {
            if (itemCatalog == null || itemCatalog.items.Count == 0) return null;
            float total = 0f;
            foreach (var i in itemCatalog.items) total += Mathf.Max(0.01f, i.weight);
            float r = Random.value * total;
            foreach (var i in itemCatalog.items)
            {
                r -= Mathf.Max(0.01f, i.weight);
                if (r <= 0f) return i;
            }
            return itemCatalog.items[itemCatalog.items.Count - 1];
        }
    }
}
