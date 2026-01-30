using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Systems
{
    [System.Serializable]
    public class DestructibleLootEntry
    {
        public GameObject prefab;
        public int minAmount = 1;
        public int maxAmount = 1;
        public float weight = 1f;
    }

    [CreateAssetMenu(fileName = "DestructibleLootTable", menuName = "ZGame/DestructibleLoot")]
    public class DestructibleLootTable : ScriptableObject
    {
        public List<DestructibleLootEntry> entries = new();

        public void Roll(Vector3 position)
        {
            if (entries == null || entries.Count == 0) return;
            float total = 0f;
            foreach (var e in entries) total += Mathf.Max(0f, e.weight);
            if (total <= 0f) return;
            float r = Random.value * total;
            float acc = 0f;
            foreach (var e in entries)
            {
                float w = Mathf.Max(0f, e.weight);
                acc += w;
                if (r <= acc)
                {
                    int amt = Random.Range(e.minAmount, e.maxAmount + 1);
                    for (int i = 0; i < amt; i++)
                    {
                        Instantiate(e.prefab, position + (Vector3)Random.insideUnitCircle * 0.2f, Quaternion.identity);
                    }
                    return;
                }
            }
        }
    }
}
