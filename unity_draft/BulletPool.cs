using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Simple bullet pool; replace with a more feature-complete pool later.
    /// </summary>
    public class BulletPool : MonoBehaviour
    {
        public Bullet prefab;
        public int initialSize = 64;
        private readonly List<Bullet> _pool = new();

        private void Awake()
        {
            for (int i = 0; i < initialSize; i++)
            {
                CreateBullet();
            }
        }

        private Bullet CreateBullet()
        {
            var b = Instantiate(prefab, transform);
            b.gameObject.SetActive(false);
            _pool.Add(b);
            return b;
        }

        public Bullet Get()
        {
            foreach (var b in _pool)
            {
                if (!b.gameObject.activeSelf)
                {
                    b.gameObject.SetActive(true);
                    return b;
                }
            }
            return CreateBullet();
        }
    }
}
