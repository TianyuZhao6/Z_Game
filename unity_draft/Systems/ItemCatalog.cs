using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Systems
{
    [CreateAssetMenu(fileName = "ItemCatalog", menuName = "ZGame/ItemCatalog")]
    public class ItemCatalog : ScriptableObject
    {
        public List<ItemPickupDef> items = new();
    }

    [System.Serializable]
    public class ItemPickupDef
    {
        public string id;
        public GameObject prefab;
        public ItemPickup.ItemType type;
        public int amount = 10;
        public string consumableId;
        public int consumableCount = 1;
        public float weight = 1f;
    }
}
