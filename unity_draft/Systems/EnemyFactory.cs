using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple factory/pool bridge for spawning enemies by string typeId.
    /// </summary>
    public class EnemyFactory : MonoBehaviour
    {
        [System.Serializable]
        public struct EnemyPrefabEntry
        {
            public string typeId;
            public Enemy prefab;
            public EnemyTypeConfig configOverride;
        }

        public GameBalanceConfig balance;
        public float spawnRadius = 10f;
        public EnemyPrefabEntry[] entries;

        private readonly Dictionary<string, EnemyPrefabEntry> _lookup = new();

        private void Awake()
        {
            foreach (var e in entries)
            {
                if (!string.IsNullOrEmpty(e.typeId) && !_lookup.ContainsKey(e.typeId))
                {
                    _lookup.Add(e.typeId, e);
                }
            }
        }

        public Enemy Spawn(string typeId, Vector3 position)
        {
            if (!_lookup.TryGetValue(typeId, out var entry) || entry.prefab == null) return null;
            var inst = Instantiate(entry.prefab, position, Quaternion.identity);
            var cfg = entry.configOverride != null ? entry.configOverride : inst.typeConfig;
            float cellSize = balance != null ? balance.cellSize : 52f;
            inst.Init(balance, cfg, cellSize);
            return inst;
        }

        public Enemy SpawnAround(string typeId, Vector3 center)
        {
            float ang = Random.Range(0f, Mathf.PI * 2f);
            Vector3 pos = center + new Vector3(Mathf.Cos(ang), Mathf.Sin(ang), 0f) * spawnRadius;
            return Spawn(typeId, pos);
        }
    }
}
