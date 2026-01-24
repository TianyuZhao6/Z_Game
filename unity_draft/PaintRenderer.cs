using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// GPU instanced renderer for PaintSystem using a simple radial mask shader.
    /// Attach alongside PaintSystem and assign a material using PaintDecal shader.
    /// </summary>
    [RequireComponent(typeof(PaintSystem))]
    public class PaintRenderer : MonoBehaviour
    {
        public PaintSystem paintSystem;
        public Material material;
        public Mesh quadMesh;
        public Camera targetCamera;

        private Matrix4x4[] _matrices;
        private Vector4[] _colors;
        private MaterialPropertyBlock _mpb;

        private void Awake()
        {
            if (paintSystem == null) paintSystem = GetComponent<PaintSystem>();
            if (material == null) material = paintSystem != null ? paintSystem.paintMaterial : null;
            if (quadMesh == null) quadMesh = CreateQuad();
            _mpb = new MaterialPropertyBlock();
            int maxBatch = paintSystem != null ? Mathf.Max(64, paintSystem.maxBatch) : 512;
            _matrices = new Matrix4x4[maxBatch];
            _colors = new Vector4[maxBatch];
            if (targetCamera == null) targetCamera = Camera.main;
        }

        private void LateUpdate()
        {
            if (paintSystem == null || material == null || quadMesh == null) return;
            var list = paintSystem.enemyPaint;
            int count = list.Count;
            if (count == 0) return;
            float baseSize = paintSystem.quadSize <= 0f ? 1f : paintSystem.quadSize;
            int idx = 0;
            while (idx < count)
            {
                int batchCount = Mathf.Min(_matrices.Length, count - idx);
                for (int i = 0; i < batchCount; i++)
                {
                    var p = list[idx + i];
                    float scale = Mathf.Max(0.1f, p.radius * 2f);
                    _matrices[i] = Matrix4x4.TRS(p.position, Quaternion.identity, new Vector3(scale, scale, 1f));
                    Color c = p.color;
                    c.a = Mathf.Clamp01(1f - (p.age / Mathf.Max(0.001f, p.lifetime)));
                    _colors[i] = c;
                }
                _mpb.SetVectorArray("_Color", _colors);
                Graphics.DrawMeshInstanced(quadMesh, 0, material, _matrices, batchCount, _mpb, UnityEngine.Rendering.ShadowCastingMode.Off, false, 0, targetCamera);
                idx += batchCount;
            }
        }

        private Mesh CreateQuad()
        {
            var m = new Mesh();
            m.vertices = new Vector3[]
            {
                new Vector3(-0.5f, -0.5f, 0f),
                new Vector3(0.5f, -0.5f, 0f),
                new Vector3(0.5f, 0.5f, 0f),
                new Vector3(-0.5f, 0.5f, 0f)
            };
            m.uv = new Vector2[]
            {
                new Vector2(0,0),
                new Vector2(1,0),
                new Vector2(1,1),
                new Vector2(0,1)
            };
            m.triangles = new int[] { 0, 1, 2, 0, 2, 3 };
            m.RecalculateNormals();
            return m;
        }
    }
}
