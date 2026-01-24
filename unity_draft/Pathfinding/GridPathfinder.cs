using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Pathfinding
{
    /// <summary>
    /// Basic grid A* pathfinder for 4-way movement. Requires a walkable grid map.
    /// </summary>
    public static class GridPathfinder
    {
        private static readonly Vector2Int[] Neighbors = new[]
        {
            new Vector2Int(1, 0), new Vector2Int(-1, 0),
            new Vector2Int(0, 1), new Vector2Int(0, -1)
        };

        public static List<Vector2Int> FindPath(bool[,] blocked, Vector2Int start, Vector2Int goal)
        {
            int w = blocked.GetLength(0);
            int h = blocked.GetLength(1);
            var open = new PriorityQueue();
            var cameFrom = new Dictionary<Vector2Int, Vector2Int>();
            var gScore = new Dictionary<Vector2Int, int>();

            open.Push(start, 0);
            gScore[start] = 0;

            while (open.Count > 0)
            {
                var current = open.Pop();
                if (current == goal)
                {
                    return Reconstruct(cameFrom, current);
                }
                foreach (var d in Neighbors)
                {
                    var next = current + d;
                    if (next.x < 0 || next.x >= w || next.y < 0 || next.y >= h) continue;
                    if (blocked[next.x, next.y]) continue;
                    int tentativeG = gScore[current] + 1;
                    if (!gScore.ContainsKey(next) || tentativeG < gScore[next])
                    {
                        gScore[next] = tentativeG;
                        int f = tentativeG + Heuristic(next, goal);
                        open.Push(next, f);
                        cameFrom[next] = current;
                    }
                }
            }
            return null;
        }

        private static List<Vector2Int> Reconstruct(Dictionary<Vector2Int, Vector2Int> cameFrom, Vector2Int current)
        {
            var path = new List<Vector2Int> { current };
            while (cameFrom.ContainsKey(current))
            {
                current = cameFrom[current];
                path.Add(current);
            }
            path.Reverse();
            return path;
        }

        private static int Heuristic(Vector2Int a, Vector2Int b)
        {
            return Mathf.Abs(a.x - b.x) + Mathf.Abs(a.y - b.y);
        }

        private class PriorityQueue
        {
            private readonly List<(Vector2Int node, int pri)> _list = new();
            public int Count => _list.Count;
            public void Push(Vector2Int node, int priority)
            {
                _list.Add((node, priority));
            }
            public Vector2Int Pop()
            {
                int best = 0;
                for (int i = 1; i < _list.Count; i++)
                {
                    if (_list[i].pri < _list[best].pri) best = i;
                }
                var n = _list[best].node;
                _list.RemoveAt(best);
                return n;
            }
        }
    }
}
