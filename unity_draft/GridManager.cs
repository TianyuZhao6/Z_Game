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
            foreach (var kv in obstacles)
            {
                Vector2Int gp = kv.Key;
                if (gp.x >= 0 && gp.x < n && gp.y >= 0 && gp.y < n)
                {
                    blocked[gp.x, gp.y] = true;
                }
            }
            navDirty = false;
            return blocked;
        }

        public void AddObstacle(Vector2Int cell, Collider2D col)
        {
            obstacles[cell] = col;
            navDirty = true;
        }

        public void RemoveObstacle(Vector2Int cell)
        {
            if (obstacles.Remove(cell))
            {
                navDirty = true;
            }
        }

        public void MarkNavDirty()
        {
            navDirty = true;
        }
    }
}
