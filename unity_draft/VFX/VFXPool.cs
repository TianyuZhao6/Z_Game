using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.VFX
{
    /// <summary>
    /// Generic VFX pool for explosions/shrapnel hits; assign prefab and reuse.
    /// </summary>
    public class VFXPool : MonoBehaviour
    {
        public ExplosionVFX explosionPrefab;
        public int initialSize = 16;
        private readonly List<ExplosionVFX> _pool = new();

        private void Awake()
        {
            for (int i = 0; i < initialSize; i++)
            {
                CreateVfx();
            }
        }

        private ExplosionVFX CreateVfx()
        {
            var v = Instantiate(explosionPrefab, transform);
            v.gameObject.SetActive(false);
            _pool.Add(v);
            return v;
        }

        public ExplosionVFX Get()
        {
            foreach (var v in _pool)
            {
                if (!v.gameObject.activeSelf)
                {
                    v.gameObject.SetActive(true);
                    return v;
                }
            }
            return CreateVfx();
        }
    }
}
