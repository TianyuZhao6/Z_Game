using UnityEngine;

namespace ZGame.UnityDraft.VFX
{
    [CreateAssetMenu(fileName = "VfxLibrary", menuName = "ZGame/VFX Library")]
    public class VfxLibrary : ScriptableObject
    {
        [System.Serializable]
        public struct Entry
        {
            public string id;
            public GameObject prefab;
        }

        public Entry[] entries;

        public GameObject Get(string id)
        {
            if (entries == null) return null;
            foreach (var e in entries)
            {
                if (e.id == id) return e.prefab;
            }
            return null;
        }
    }
}
