// Derive spamoor's child wallet addresses for a root key and wallet seed.
//
//	children <root-privkey-hex> <seed> <count>
//
// Mirrors spamoor f3b5828 walletpool.go prepareChildWallet:
//
//	childKey = sha256(rootPrivKeyBytes || bigEndianUint64(childIdx) || []byte(seed))
package main

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/ethereum/go-ethereum/crypto"
)

func main() {
	if len(os.Args) != 4 {
		fmt.Fprintln(os.Stderr, "usage: children <root-privkey-hex> <seed> <count>")
		os.Exit(2)
	}
	rootHex := strings.TrimPrefix(os.Args[1], "0x")
	seed := os.Args[2]
	count, err := strconv.Atoi(os.Args[3])
	if err != nil {
		panic(err)
	}

	rootKey, err := crypto.HexToECDSA(rootHex)
	if err != nil {
		panic(err)
	}
	parent := crypto.FromECDSA(rootKey)

	for i := 0; i < count; i++ {
		idxBytes := make([]byte, 8)
		binary.BigEndian.PutUint64(idxBytes, uint64(i))
		if seed != "" {
			idxBytes = append(idxBytes, []byte(seed)...)
		}
		childKey := sha256.Sum256(append(append([]byte{}, parent...), idxBytes...))
		child, err := crypto.HexToECDSA(fmt.Sprintf("%x", childKey))
		if err != nil {
			panic(err)
		}
		fmt.Printf("%d %s 0x%x\n", i, crypto.PubkeyToAddress(child.PublicKey).Hex(),
			crypto.FromECDSA(child))
	}
}
