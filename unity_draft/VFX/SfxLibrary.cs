using UnityEngine;

namespace ZGame.UnityDraft.VFX
{
    [CreateAssetMenu(fileName = "SfxLibrary", menuName = "ZGame/SFX Library")]
    public class SfxLibrary : ScriptableObject
    {
        [System.Serializable]
        public struct Entry
        {
            public string id;
            public AudioClip clip;
        }

        public Entry[] entries;

        public AudioClip Get(string id)
        {
            if (entries == null) return null;
            foreach (var e in entries)
            {
                if (e.id == id) return e.clip;
            }
            return null;
        }
    }
}
