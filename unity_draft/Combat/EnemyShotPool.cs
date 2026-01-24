using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Combat
{
    /// <summary>
    /// Separate pool for enemy shots if you want distinct visuals/materials.
    /// </summary>
    public class EnemyShotPool : MonoBehaviour
    {
        public EnemyShot prefab;
        public int initialSize = 32;
        private readonly List<EnemyShot> _pool = new();

        private void Awake()
        {
            for (int i = 0; i < initialSize; i++)
            {
                CreateShot();
            }
        }

        private EnemyShot CreateShot()
        {
            var s = Instantiate(prefab, transform);
            s.gameObject.SetActive(false);
            _pool.Add(s);
            return s;
        }

        public EnemyShot Get()
        {
            foreach (var s in _pool)
            {
                if (!s.gameObject.activeSelf)
                {
                    s.gameObject.SetActive(true);
                    return s;
                }
            }
            return CreateShot();
        }
    }
}
