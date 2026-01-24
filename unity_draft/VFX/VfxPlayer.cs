using UnityEngine;

namespace ZGame.UnityDraft.VFX
{
    /// <summary>
    /// Lightweight VFX spawner using a library lookup.
    /// </summary>
    public class VfxPlayer : MonoBehaviour
    {
        public VfxLibrary library;
        public VFXPool pool;

        public GameObject Play(string id, Vector3 pos, Transform parent = null)
        {
            GameObject prefab = library != null ? library.Get(id) : null;
            if (prefab == null) return null;
            if (pool != null)
            {
                var v = pool.Get();
                v.transform.position = pos;
                v.gameObject.SetActive(true);
                return v.gameObject;
            }
            var go = Instantiate(prefab, pos, Quaternion.identity, parent);
            go.SetActive(true);
            return go;
        }
    }
}
