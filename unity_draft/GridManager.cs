using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Minimal grid helper mirroring GRID_SIZE/CELL_SIZE usage in ZGame.py.
    /// Handles grid->world conversions and obstacle bookkeeping.
    /// </summary>
    public class GridManager : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public Transform obstacleParent;

        [Tooltip("Obstacles keyed by grid (x,y).")]
        public Dictionary<Vector2Int, Collider2D> obstacles = new();
        public bool navDirty = true;
        public event System.Action OnNavDirty;

        public Vector3 GridToWorldCenter(Vector2Int cell)
        {
            float cs = balance != null ? balance.cellSize : 1f;
            return new Vector3(cell.x * cs + cs * 0.5f, cell.y * cs + cs * 0.5f, 0f);
        }

        public Vector2Int WorldToGrid(Vector3 world)
        {
            float cs = balance != null ? balance.cellSize : 1f;
            return new Vector2Int(Mathf.FloorToInt(world.x / cs), Mathf.FloorToInt(world.y / cs));
        }

        /// <summary>
        /// Placeholder: generate obstacles based on density. Replace with your level generator.
        /// </summary>
        public void GenerateObstacles()
        {
            obstacles.Clear();
            // TODO: port obstacle placement from ZGame.py generate_game_entities
            navDirty = true;
        }

        /// <summary>
        /// Builds a blocked grid mask from current obstacles.
        /// </summary>
        public bool[,] BuildBlockedGrid()
        {
            int n = balance != null ? balance.gridSize : 0;
            bool[,] blocked = new bool[n, n];
            if (obstacles != null)
            {
                foreach (var kv in obstacles)
                {
                    Vector2Int gp = kv.Key;
                    if (gp.x >= 0 && gp.x < n && gp.y >= 0 && gp.y < n)
                    {
                        blocked[gp.x, gp.y] = true;
                    }
                }
            }
            navDirty = false;
            return blocked;
        }

        public void AddObstacle(Vector2Int cell, Collider2D col)
        {
            obstacles[cell] = col;
            navDirty = true;
            OnNavDirty?.Invoke();
        }

        public void AddObstacle(Vector3 worldPos, float radius = 0f)
        {
            var cell = WorldToGrid(worldPos);
            AddObstacle(cell, null);
        }

        public void RemoveObstacle(Vector3 worldPos)
        {
            var cell = WorldToGrid(worldPos);
            RemoveObstacle(cell);
        }

        public bool IsBlocked(Vector3 worldPos)
        {
            var cell = WorldToGrid(worldPos);
            return obstacles.ContainsKey(cell);
        }

        public void RemoveObstacle(Vector2Int cell)
        {
            if (obstacles.Remove(cell))
            {
                navDirty = true;
                OnNavDirty?.Invoke();
            }
        }

        public void MarkNavDirty()
        {
            navDirty = true;
            OnNavDirty?.Invoke();
        }

        public bool IsClearWithRadius(Vector3 worldPos, float radiusPx)
        {
            float cs = balance != null ? balance.cellSize : 1f;
            int cells = Mathf.CeilToInt(radiusPx / cs);
            var center = WorldToGrid(worldPos);
            for (int dx = -cells; dx <= cells; dx++)
            {
                for (int dy = -cells; dy <= cells; dy++)
                {
                    var c = new Vector2Int(center.x + dx, center.y + dy);
                    if (obstacles.ContainsKey(c)) return false;
                }
            }
            return true;
        }

        public bool IsNearBlocked(Vector3 worldPos, float buffer)
        {
            float cs = balance != null ? balance.cellSize : 1f;
            int cells = Mathf.CeilToInt(buffer / cs);
            var center = WorldToGrid(worldPos);
            for (int dx = -cells; dx <= cells; dx++)
            {
                for (int dy = -cells; dy <= cells; dy++)
                {
                    var c = new Vector2Int(center.x + dx, center.y + dy);
                    if (obstacles.ContainsKey(c)) return true;
                }
            }
            return false;
        }
    }
}
