using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Placeholder paint/ink system. Replace with a GPU decal/RenderTexture path later.
    /// Currently tracks footprint instances and could be rendered as pooled sprites.
    /// </summary>
    public class PaintSystem : MonoBehaviour
    {
        [System.Serializable]
        public class PaintInstance
        {
            public Vector2 position;
            public float radius;
            public float lifetime;
            public float age;
            public Color color;
        }

        public List<PaintInstance> enemyPaint = new();
        [Header("Rendering")]
        public bool gpuRender = true;
        public Material paintMaterial;
        public float quadSize = 1f;
        public int maxBatch = 512;

        public void SpawnEnemyPaint(Vector2 pos, float radius, float lifetime, Color color)
        {
            enemyPaint.Add(new PaintInstance
            {
                position = pos,
                radius = radius,
                lifetime = lifetime,
                age = 0f,
                color = color
            });
        }

        private void Update()
        {
            float dt = Time.deltaTime;
            for (int i = enemyPaint.Count - 1; i >= 0; i--)
            {
                var p = enemyPaint[i];
                p.age += dt;
                if (p.age >= p.lifetime)
                {
                    enemyPaint.RemoveAt(i);
                }
                else
                {
                    enemyPaint[i] = p;
                }
            }
        }
    }
}
