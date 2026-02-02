using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple fog-of-war overlay: darkens the screen, revealing a soft circle around the player.
    /// Requires a material using the FogMask shader on a full-screen quad.
    /// </summary>
    [RequireComponent(typeof(MeshRenderer))]
    public class FogController : MonoBehaviour
    {
        public Transform target;
        public Camera cam;
        public Material fogMaterial;
        [Range(0f, 1f)] public float radius = 0.25f;   // in viewport units
        [Range(0f, 0.5f)] public float softness = 0.15f;
        public Color fogColor = new Color(0f, 0f, 0f, 0.8f);

        private MeshRenderer _mr;

        private void Awake()
        {
            _mr = GetComponent<MeshRenderer>();
            if (cam == null) cam = Camera.main;
            if (_mr != null && fogMaterial != null) _mr.material = fogMaterial;
        }

        private void LateUpdate()
        {
            if (fogMaterial == null || cam == null || target == null) return;
            Vector3 vp = cam.WorldToViewportPoint(target.position);
            fogMaterial.SetVector("_Center", new Vector4(vp.x, vp.y, 0, 0));
            fogMaterial.SetFloat("_Radius", radius);
            fogMaterial.SetFloat("_Softness", softness);
            fogMaterial.SetColor("_FogColor", fogColor);
        }
    }
}
