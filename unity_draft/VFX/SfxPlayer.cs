using UnityEngine;

namespace ZGame.UnityDraft.VFX
{
    /// <summary>
    /// Simple audio player that looks up clips by id.
    /// </summary>
    public class SfxPlayer : MonoBehaviour
    {
        public SfxLibrary library;
        public float volume = 1f;

        public void Play(string id, Vector3 pos)
        {
            var clip = library != null ? library.Get(id) : null;
            if (clip != null) AudioSource.PlayClipAtPoint(clip, pos, volume);
        }
    }
}
